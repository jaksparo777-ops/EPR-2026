
    const itemsMaster = JSON.parse(document.getElementById('item-data').textContent);
    const stockMaster = JSON.parse(document.getElementById('stock-data').textContent);
    const capacityMaster = JSON.parse(document.getElementById('set-capacity-data').textContent);
    const allocationsMaster = JSON.parse(document.getElementById('allocation-data').textContent || '[]');
    const workerWIPByItem = {{ worker_wip_by_item_json|safe }};
    const smartAllocations = {{ smart_allocations|safe }};
    let rowCount = 0;
    let workerTS = null;
    let originalWorkers = [];
    const rowTomSelects = {};
    let lastAllocatedItemId = null;

    let isAutoSelectingWorker = false;

    function filterWorkersBySelectedItems() {
        if (!workerTS || originalWorkers.length === 0) return;

        const selectedItemIds = Object.keys(rowTomSelects)
            .map(id => rowTomSelects[id].getValue())
            .filter(val => val !== "");

        if (selectedItemIds.length === 0) {
            const currentVal = workerTS.getValue();
            workerTS.clearOptions();
            workerTS.addOptions(originalWorkers);
            if (currentVal) {
                workerTS.setValue(currentVal, true);
            }
            return;
        }

        let commonWorkerIds = null;
        selectedItemIds.forEach(itemId => {
            let workersForItem = smartAllocations[itemId] || [];
            
            // Fallback: check active pending WIP workers
            if (workersForItem.length === 0 && typeof workerWipByItem !== 'undefined') {
                const wipWorkers = [];
                originalWorkers.forEach(w => {
                    const key = `${w.id}_${itemId}`;
                    if (workerWipByItem[key] && workerWipByItem[key] > 0) {
                        wipWorkers.push({ id: w.id, name: w.name });
                    }
                });
                if (wipWorkers.length > 0) {
                    workersForItem = wipWorkers;
                }
            }

            const workerIdsSet = new Set(workersForItem.map(w => w.id));
            if (commonWorkerIds === null) {
                commonWorkerIds = workerIdsSet;
            } else {
                commonWorkerIds = new Set([...commonWorkerIds].filter(wId => workerIdsSet.has(wId)));
            }
        });

        const filteredWorkers = originalWorkers.filter(w => commonWorkerIds && commonWorkerIds.has(w.id));
        const currentVal = workerTS.getValue();
        workerTS.clearOptions();

        if (filteredWorkers.length > 0) {
            workerTS.addOptions(filteredWorkers);
            const exists = filteredWorkers.some(w => w.id === currentVal);
            if (exists) {
                workerTS.setValue(currentVal, true);
            } else {
                const autoWorkerId = filteredWorkers[0].id;
                isAutoSelectingWorker = true;
                workerTS.setValue(autoWorkerId);
                isAutoSelectingWorker = false;
            }
        } else {
            workerTS.addOptions(originalWorkers);
            if (currentVal) {
                workerTS.setValue(currentVal, true);
            }
        }
    }

    function recalculateAllRows() {
        Object.keys(rowTomSelects).forEach(id => {
            calculateRow(id);
        });
    }

    function toggleDirection() {
        const container = document.querySelector('.dir-toggle-pill');
        const input = document.getElementById('dirInput');
        const current = container.dataset.dir;

        const boxContainer = document.getElementById('autoAdjustVarianceContainer');

        if (current === 'polishing_out') {
            container.dataset.dir = 'polishing_in';
            input.value = 'polishing_in';
            document.getElementById('opt-out').classList.remove('active');
            document.getElementById('opt-in').classList.add('active');
            if (boxContainer) {
                boxContainer.style.display = 'flex';
            }
        } else {
            container.dataset.dir = 'polishing_out';
            input.value = 'polishing_out';
            document.getElementById('opt-in').classList.remove('active');
            document.getElementById('opt-out').classList.add('active');
            if (boxContainer) {
                boxContainer.style.display = 'none';
                const defaultRadio = boxContainer.querySelector('input[value="none"]');
                if (defaultRadio) defaultRadio.checked = true;
            }
        }
        recalculateAllRows();
    }

    function togglePackaging(id, pkgType) {
        const regBtn = document.getElementById(`pkg-reg-${id}`);
        const boxBtn = document.getElementById(`pkg-box-${id}`);
        const pkgInput = document.getElementById(`pkg-input-${id}`);
        
        pkgInput.value = pkgType;
        pkgInput.dataset.pkg = pkgType;
        
        if (pkgType === 'box') {
            regBtn.style.background = 'transparent';
            regBtn.style.color = 'var(--text-secondary)';
            regBtn.style.border = 'none';
            boxBtn.style.background = 'rgba(255,255,255,0.05)';
            boxBtn.style.color = '#fbbf24';
            boxBtn.style.border = '1px solid rgba(251, 191, 36, 0.2)';
        } else {
            boxBtn.style.background = 'transparent';
            boxBtn.style.color = 'var(--text-secondary)';
            boxBtn.style.border = 'none';
            regBtn.style.background = 'rgba(255,255,255,0.05)';
            regBtn.style.color = 'white';
            regBtn.style.border = 'none';
        }
        
        // Recalculate row
        calculateRow(id);
    }

    // (Entry mode switching removed in favor of Unified mixed-mode transaction builder)

    function switchMainTab(tab) {
        document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

        document.getElementById(tab + '-section').style.display = 'block';
        
        if (typeof event !== 'undefined' && event && event.currentTarget) {
            event.currentTarget.classList.add('active');
        } else {
            const tabBtn = document.querySelector(`.nav-tab[onclick*="switchMainTab('${tab}')"]`);
            if (tabBtn) tabBtn.classList.add('active');
        }
    }

    function getAllowedItemsForWorker(workerId) {
        if (!workerId) return itemsMaster;

        const cleanId = workerId.replace(/^(w_|jw_)/, '');

        const allowed = itemsMaster.filter(it => {
            const performers = smartAllocations[it.id.toString()] || [];
            if (performers.some(p => p.id === workerId || p.id.replace(/^(w_|jw_)/, '') === cleanId)) return true;

            if (it.is_set && it.components && it.components.length > 0) {
                return it.components.some(c => {
                    const cPerformers = smartAllocations[c.id.toString()] || [];
                    return cPerformers.some(p => p.id === workerId || p.id.replace(/^(w_|jw_)/, '') === cleanId);
                });
            }
            return false;
        });

        if (allowed.length > 0) return allowed;

        // Fallback: allocationsMaster with clean ID matching
        const allocatedIds = allocationsMaster.filter(a => {
            const aClean = a.worker_id.replace(/^(w_|jw_)/, '');
            return aClean === cleanId;
        }).map(a => a.item_id.toString());

        const allowedItemIds = new Set(allocatedIds);
        itemsMaster.forEach(it => {
            if (it.is_set && it.components && it.components.length > 0) {
                const hasAllocatedComponent = it.components.some(c => allowedItemIds.has(c.id.toString()));
                if (hasAllocatedComponent) {
                    allowedItemIds.add(it.id.toString());
                }
            }
        });

        const fallbackAllowed = itemsMaster.filter(it => allowedItemIds.has(it.id.toString()));
        return fallbackAllowed.length > 0 ? fallbackAllowed : itemsMaster;
    }

    const rowItemTypeFilters = {};

    function updateRowItemOptions(id, workerId, typeFilter) {
        const ts = rowTomSelects[id];
        if (!ts) return;

        let allowedItems = getAllowedItemsForWorker(workerId);

        if (typeFilter === 'set') {
            allowedItems = allowedItems.filter(it => it.is_set);
        } else if (typeFilter === 'single') {
            allowedItems = allowedItems.filter(it => !it.is_set);
        }

        const currentVal = ts.getValue();

        if (currentVal && !allowedItems.some(it => it.id == currentVal)) {
            const curItem = itemsMaster.find(it => it.id == currentVal);
            if (curItem) {
                allowedItems.unshift(curItem);
            }
        }

        ts.clearOptions();

        const subCategories = new Set();
        allowedItems.forEach(it => {
            const sub = it.category === 'OTHER' ? (it.is_set ? 'SETS' : 'SINGLES') : (it.sub_category || it.subCategory || 'OTHER');
            subCategories.add(sub);
        });

        const optionsToAdd = allowedItems.map(it => {
            const sub = it.category === 'OTHER' ? (it.is_set ? 'SETS' : 'SINGLES') : (it.sub_category || it.subCategory || 'OTHER');
            return {
                value: it.id,
                text: `${it.is_set ? '📦 [SET] ' : '🧩 [SINGLE] '}${it.code} - ${it.name}`,
                category: it.category || 'OTHER',
                subCategory: sub
            };
        });

        ts.addOptions(optionsToAdd);
        if (currentVal) {
            ts.setValue(currentVal, true);
        } else {
            ts.setValue('', true);
        }
    }

    function toggleItemTypeFilter(id, type) {
        rowItemTypeFilters[id] = type;
        const btnSet = document.getElementById(`type-set-${id}`);
        const btnSingle = document.getElementById(`type-single-${id}`);

        if (type === 'set') {
            if (btnSet) {
                btnSet.style.background = '#fbbf24';
                btnSet.style.color = '#000';
            }
            if (btnSingle) {
                btnSingle.style.background = 'transparent';
                btnSingle.style.color = 'var(--text-secondary)';
            }
        } else {
            if (btnSingle) {
                btnSingle.style.background = '#3b82f6';
                btnSingle.style.color = '#fff';
            }
            if (btnSet) {
                btnSet.style.background = 'transparent';
                btnSet.style.color = 'var(--text-secondary)';
            }
        }

        const workerId = workerTS ? workerTS.getValue() : '';
        updateRowItemOptions(id, workerId, type);
    }

    function filterPolishingItemsByWorker(workerId) {
        Object.keys(rowTomSelects).forEach(id => {
            const typeFilter = rowItemTypeFilters[id] || 'set';
            updateRowItemOptions(id, workerId, typeFilter);
        });
    }

    function addItemRow() {
        const id = rowCount++;
        rowItemTypeFilters[id] = 'set';

        const workerId = workerTS ? workerTS.getValue() : '';
        let allowedItems = getAllowedItemsForWorker(workerId).filter(it => it.is_set);

        console.log(`Adding dynamic item row. SET items count: ${allowedItems.length}`);

        const html = `
            <div class="item-row" id="row-${id}" style="border-left: 4px solid #fbbf24; padding: 20px;">
                <div class="remove-row-btn" onclick="removeRow(${id})" style="top: 10px; right: 10px;">×</div>
                
                <!-- Row 1: SELECT ITEM / SET with SET vs SINGLE Toggle Pill -->
                <div style="margin-bottom: 16px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
                        <label class="stat-label" style="margin-bottom:0;">SELECT ITEM / SET</label>
                        <div class="item-type-toggle-pill" style="display:flex; background:rgba(0,0,0,0.3); border:1px solid var(--glass-border); border-radius:8px; padding:2px; height:28px; align-items:center;">
                            <button type="button" class="type-btn active" id="type-set-${id}" onclick="toggleItemTypeFilter(${id}, 'set')" style="padding:2px 10px; height:24px; border-radius:6px; font-size:10px; font-weight:800; border:none; background:#fbbf24; color:#000; cursor:pointer; transition:0.2s;">📦 SET</button>
                            <button type="button" class="type-btn" id="type-single-${id}" onclick="toggleItemTypeFilter(${id}, 'single')" style="padding:2px 10px; height:24px; border-radius:6px; font-size:10px; font-weight:800; border:none; background:transparent; color:var(--text-secondary); cursor:pointer; transition:0.2s;">🧩 SINGLE</button>
                        </div>
                    </div>
                    <select name="item[]" class="item-select" onchange="handleItemChange(${id}, this)">
                        <option value="">Search...</option>
                        ${allowedItems.map(it => `<option value="${it.id}">${it.is_set ? '📦 [SET] ' : '🧩 [SINGLE] '}${it.code} - ${it.name}</option>`).join('')}
                    </select>
                </div>
                
                <!-- Row 2: Inputs (Packaging on top, Lots and Extra Pieces below in a subgrid) -->
                <div id="pkg-container-${id}" style="margin-bottom: 12px;">
                    <label class="stat-label">PACKAGING</label>
                    <div style="display:flex; background:rgba(0,0,0,0.2); border:1px solid var(--glass-border); border-radius:10px; padding:2px; height:38px; align-items:center;">
                        <button type="button" class="pkg-btn active pkg-regular-btn" style="flex:1; height:32px; border-radius:8px; font-size:10px; font-weight:800; border:none; background:rgba(255,255,255,0.05); color:white; cursor:pointer;" id="pkg-reg-${id}" onclick="togglePackaging(${id}, 'regular')">REGULAR</button>
                        <button type="button" class="pkg-btn pkg-box-btn" style="flex:1; height:32px; border-radius:8px; font-size:10px; font-weight:800; border:none; background:transparent; color:var(--text-secondary); cursor:pointer;" id="pkg-box-${id}" onclick="togglePackaging(${id}, 'box')">BOX</button>
                    </div>
                    <input type="hidden" name="packaging[]" id="pkg-input-${id}" class="pkg-toggle-pill" data-pkg="regular" value="regular">
                </div>
                
                <div id="input-grid-${id}" style="display:grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; align-items: end;">
                    <div class="input-group" id="lot-container-${id}" style="margin-bottom:0;">
                        <label class="stat-label" id="lot-label-${id}">BULK LOTS <span style="font-size:8px; color:var(--text-secondary); font-weight:normal;" id="lot-size-span-${id}">(Lot: 0)</span></label>
                        <input type="number" name="lots[]" value="0" min="0" oninput="calculateRow(${id})" style="height:38px; margin:0;">
                    </div>
                    
                    <div class="input-group" id="extra-group-${id}" style="margin-bottom:0;">
                        <label class="stat-label" id="extra-label-${id}">+ EXTRA PCS</label>
                        <input type="number" name="manual[]" value="0" min="0" oninput="calculateRow(${id})" style="height:38px; margin:0;">
                    </div>
                </div>

                <!-- Row 3: Display Summary Grid -->
                <div class="row-grid" style="margin-top:16px; border-top:1px solid var(--glass-border); padding-top:16px; grid-template-columns: 1fr 1.4fr 1fr;">
                    <div>
                        <div class="stat-label">TOTAL QTY</div>
                        <div class="stat-value"><span id="qty-display-${id}">0</span> pcs</div>
                    </div>
                    <div>
                        <div class="stat-label">AVAIL STOCK</div>
                        <div class="stat-value" style="color: #fbbf24; font-size: 15px;"><span id="avail-display-${id}">0</span></div>
                    </div>
                    <div>
                        <div class="stat-label">WEIGHT</div>
                        <div class="stat-value"><span id="wt-display-${id}">0.000</span> kg</div>
                        <input type="hidden" name="weight[]" id="wt-input-${id}" value="0">
                    </div>
                </div>

                <div id="bom-display-${id}" class="bom-indicator"></div>

                <!-- Dynamic components overrides -->
                <div id="components-drawer-${id}" style="margin-top:16px; border-top:1px dashed var(--glass-border); padding-top:16px; display:none;">
                    <div class="stat-label" style="color:var(--accent-gold); margin-bottom:12px; font-size:11px;">📦 Set Components overrides</div>
                    <div id="components-list-${id}" style="display:flex; flex-direction:column; gap:12px;"></div>
                </div>
            </div>
        `;

        document.getElementById('items-container').insertAdjacentHTML('beforeend', html);

        const subCategories = new Set();
        allowedItems.forEach(it => {
            const sub = it.category === 'OTHER' ? (it.is_set ? 'SETS' : 'SINGLES') : (it.sub_category || it.subCategory || 'OTHER');
            subCategories.add(sub);
        });
        const optgroups = Array.from(subCategories).map(sub => ({
            value: sub,
            label: sub.toUpperCase()
        }));

        const ts = new TomSelect(`#row-${id} .item-select`, {
            create: false,
            valueField: 'value',
            labelField: 'text',
            searchField: ['text'],
            options: allowedItems.map(it => {
                const sub = it.category === 'OTHER' ? (it.is_set ? 'SETS' : 'SINGLES') : (it.sub_category || it.subCategory || 'OTHER');
                return {
                    value: it.id,
                    text: `${it.is_set ? '📦 [SET] ' : '🧩 [SINGLE] '}${it.code} - ${it.name}`,
                    category: it.category || 'OTHER',
                    subCategory: sub
                };
            }),
            optgroups: optgroups,
            optgroupField: 'subCategory',
            placeholder: 'Search...',
            allowEmptyOption: true,
            score: function(search) {
                search = search.toLowerCase().trim();
                return function(item) {
                    if (!search) return 1;
                    const text = item.text.toLowerCase();
                    const cleanCode = item.text.replace(/^🧩 \[SINGLE\]\s*|^📦 \[SET\]\s*/i, '').toLowerCase().trim();
                    if (cleanCode.startsWith(search)) {
                        return 10;
                    } else if (text.includes(search)) {
                        return 1;
                    }
                    return 0;
                };
            },
            render: {
                no_results: function(data, escape) {
                    const filterType = rowItemTypeFilters[id] || 'set';
                    if (filterType === 'set') {
                        return `<div class="no-results" style="padding:14px; font-size:12px; color:var(--text-secondary); text-align:center;">
                                    No SET items matching "<b>${escape(data.input)}</b>".<br>
                                    <button type="button" onclick="toggleItemTypeFilter(${id}, 'single')" style="margin-top:8px; background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); padding:4px 10px; border-radius:6px; font-size:11px; font-weight:bold; cursor:pointer;">
                                        👉 Switch to [🧩 SINGLE] items
                                    </button>
                                </div>`;
                    }
                    return `<div class="no-results" style="padding:12px; font-size:12px; color:var(--text-secondary); text-align:center;">No items found matching "${escape(data.input)}"</div>`;
                }
            }
        });
        rowTomSelects[id] = ts;

        // Ensure TomSelect change reliably triggers handleItemChange and recalculates quantities
        ts.on('change', function() {
            const selectEl = document.querySelector(`#row-${id} .item-select`);
            if (selectEl && selectEl.nextElementSibling) {
                selectEl.nextElementSibling.style.border = '';
                selectEl.nextElementSibling.style.boxShadow = '';
            }
            handleItemChange(id);
        });
    }

    function removeRow(id) {
        document.getElementById(`row-${id}`).remove();
        delete rowTomSelects[id];
    }

    function handleItemChange(id) {
        const compList = document.getElementById(`components-list-${id}`);
        if (compList) {
            compList.innerHTML = '';
        }

        filterWorkersBySelectedItems();

        calculateRow(id);
    }

    function calculateRow(id) {
        const row = document.getElementById(`row-${id}`);
        if (!row) return;
        const ts = rowTomSelects[id];
        const selectedValue = ts ? ts.getValue() : '';
        const lots = parseInt(row.querySelector('[name="lots[]"]').value || 0);
        const extra = parseInt(row.querySelector('[name="manual[]"]').value || 0);
        const bomDisplay = document.getElementById(`bom-display-${id}`);
        const pkgType = document.getElementById(`pkg-input-${id}`).value;

        const pkgContainer = document.getElementById(`pkg-container-${id}`);
        const lotContainer = document.getElementById(`lot-container-${id}`);
        const extraGroup = document.getElementById(`extra-group-${id}`);
        const extraLabel = document.getElementById(`extra-label-${id}`);
        const inputGrid = document.getElementById(`input-grid-${id}`);
        const lotsInput = row.querySelector('[name="lots[]"]');
        const manualInput = row.querySelector('[name="manual[]"]');

        const item = itemsMaster.find(it => it.id == selectedValue);
        if (!item) {
            document.getElementById(`lot-size-span-${id}`).innerText = '(Lot: 0)';
            document.getElementById(`components-drawer-${id}`).style.display = 'none';
            document.getElementById(`qty-display-${id}`).innerText = 0;
            const availEl = document.getElementById(`avail-display-${id}`);
            if (availEl) availEl.innerText = '0';
            document.getElementById(`wt-display-${id}`).innerText = '0.000';
            document.getElementById(`wt-input-${id}`).value = 0;
            bomDisplay.innerHTML = '';

            if (pkgContainer) pkgContainer.style.display = 'block';
            if (lotContainer) lotContainer.style.display = 'block';
            if (extraGroup) extraGroup.style.display = 'block';
            if (extraLabel) extraLabel.innerText = '+ EXTRA PCS';
            if (inputGrid) inputGrid.style.gridTemplateColumns = '1fr 1fr';
            return;
        }

        // Update lot size multiplier based on packaging choice (with fallback to lot_size if lot_with_box is 0/undefined)
        let lotSize = item.lot_size || 1;
        if (pkgType === 'box') {
            lotSize = (item.lot_with_box && item.lot_with_box > 0) ? item.lot_with_box : (item.lot_size || 1);
        }
        document.getElementById(`lot-size-span-${id}`).innerText = `(Lot: ${lotSize})`;

        // Visual feedback based on item type
        row.style.borderLeftColor = item.is_set ? '#6366f1' : '#fbbf24';

        let currentLots = lots;
        let currentExtra = extra;

        if (item.is_set) {
            // SET Item: Show Packaging, Lots, and Extra Pcs
            if (pkgContainer) pkgContainer.style.display = 'block';
            if (lotContainer) lotContainer.style.display = 'block';
            if (extraGroup) extraGroup.style.display = 'block';
            if (extraLabel) extraLabel.innerText = '+ EXTRA PCS';
            if (inputGrid) inputGrid.style.gridTemplateColumns = '1fr 1fr';
        } else {
            // SINGLE Item: Hide Packaging & Lots, Show ONLY Extra Pcs renamed to "PCS"
            if (pkgContainer) pkgContainer.style.display = 'none';
            if (lotContainer) lotContainer.style.display = 'none';
            if (extraGroup) extraGroup.style.display = 'block';
            if (extraLabel) extraLabel.innerText = 'PCS';
            if (inputGrid) inputGrid.style.gridTemplateColumns = '1fr';
            if (lotsInput) lotsInput.value = 0;
            currentLots = 0;
        }

        const totalQty = (currentLots * lotSize) + currentExtra;
        const totalWt = (totalQty * item.weight).toFixed(3);

        document.getElementById(`qty-display-${id}`).innerText = totalQty;
        document.getElementById(`wt-display-${id}`).innerText = totalWt;
        document.getElementById(`wt-input-${id}`).value = totalWt;

        // Calculate Available Stock
        const dirInput = document.getElementById('dirInput');
        const direction = dirInput ? dirInput.value : 'polishing_out';
        let availDisplay = '0';

        if (item.is_set) {
            let capacity = 0;
            if (direction === 'polishing_out') {
                capacity = capacityMaster[selectedValue] || 0;
            } else {
                const workerId = workerTS ? workerTS.getValue() : '';
                const key = `${workerId}_${selectedValue}`;
                capacity = workerWIPByItem[key] || 0;
            }
            
            const activePkgType = document.getElementById(`pkg-input-${id}`).value;
            let currentLotSize = item.lot_size || 1;
            if (activePkgType === 'box') {
                currentLotSize = (item.lot_with_box && item.lot_with_box > 0) ? item.lot_with_box : (item.lot_size || 1);
            }
            if (currentLotSize <= 0) currentLotSize = 1;

            const availLots = Math.floor(capacity / currentLotSize);
            const remainder = capacity % currentLotSize;

            if (remainder === 0) {
                availDisplay = `${availLots} Lots (${capacity} Sets)`;
            } else {
                availDisplay = `${availLots} L, ${remainder} S (${capacity} Sets)`;
            }
        } else {
            let availQty = 0;
            if (direction === 'polishing_out') {
                availQty = stockMaster[selectedValue] || 0;
            } else {
                const workerId = workerTS ? workerTS.getValue() : '';
                const key = `${workerId}_${selectedValue}`;
                availQty = workerWIPByItem[key] || 0;
            }

            const activePkgType = document.getElementById(`pkg-input-${id}`).value;
            let currentLotSize = item.lot_size || 1;
            if (activePkgType === 'box') {
                currentLotSize = (item.lot_with_box && item.lot_with_box > 0) ? item.lot_with_box : (item.lot_size || 1);
            }
            if (currentLotSize <= 0) currentLotSize = 1;

            const availLots = Math.floor(availQty / currentLotSize);
            const remainder = availQty % currentLotSize;

            if (remainder === 0) {
                availDisplay = `${availLots} Lots (${availQty} pcs)`;
            } else {
                availDisplay = `${availLots} L, ${remainder} P (${availQty} pcs)`;
            }
        }

        const availEl = document.getElementById(`avail-display-${id}`);
        if (availEl) {
            availEl.innerText = availDisplay;
        }

        // Render BOM/Set components overrides if it's a SET
        const compDrawer = document.getElementById(`components-drawer-${id}`);
        const compList = document.getElementById(`components-list-${id}`);

        if (item.is_set && item.components.length > 0) {
            compDrawer.style.display = 'block';

            if (compList.children.length === 0) {
                compList.innerHTML = item.components.map(c => {
                    const available = stockMaster[c.id] || 0;
                    return `
                        <div class="comp-row-override" id="comp-row-${id}-${c.id}" data-comp-id="${c.id}" data-qty-per-set="${c.qty_per_set}">
                            <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); border:1px solid var(--glass-border); padding:10px 14px; border-radius:12px; flex-wrap:wrap; gap:10px;">
                                <div style="flex:1; min-width:150px;">
                                    <div style="font-size:12px; font-weight:700; color:white;">${c.name}</div>
                                    <div style="font-size:10px; color:var(--text-secondary);">Stock: <span id="comp-stock-val-${id}-${c.id}">${available}</span> pcs</div>
                                </div>
                                <div style="width:100px;">
                                    <div class="stat-label" style="font-size:9px; margin-bottom:4px;">Calc Qty</div>
                                    <div style="font-size:13px; font-weight:700; color:var(--indigo-primary);"><span id="comp-calc-qty-${id}-${c.id}">0</span> pcs</div>
                                </div>
                                <div class="input-group" style="width:110px;">
                                    <label class="stat-label" style="font-size:9px; margin-bottom:2px;">+ Extra pcs</label>
                                    <input type="number" class="comp-extra-input" value="0" min="0" style="height:32px; font-size:11px; padding:4px 8px; border-radius:8px; background:rgba(0,0,0,0.2); border:1px solid var(--glass-border); color:white; text-align:center;" oninput="calculateRow(${id})">
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            // Update nested components calculated amounts
            item.components.forEach(c => {
                const calcQty = c.qty_per_set * totalQty;
                const compRow = document.getElementById(`comp-row-${id}-${c.id}`);
                const extraInput = compRow.querySelector('.comp-extra-input');
                const extraVal = parseInt(extraInput.value || 0);
                const totalCompQty = calcQty + extraVal;

                document.getElementById(`comp-calc-qty-${id}-${c.id}`).innerText = totalCompQty;

                // Validation against machining stock
                const available = stockMaster[c.id] || 0;
                const containerDiv = compRow.querySelector('div');
                if (totalCompQty > available) {
                    containerDiv.style.borderColor = 'rgba(239, 68, 68, 0.4)';
                    containerDiv.style.background = 'rgba(239, 68, 68, 0.05)';
                } else {
                    containerDiv.style.borderColor = 'var(--glass-border)';
                    containerDiv.style.background = 'rgba(255,255,255,0.02)';
                }
            });

            bomDisplay.innerHTML = '';
        } else {
            compDrawer.style.display = 'none';
            compList.innerHTML = '';
            bomDisplay.innerHTML = '';
        }
    }

    function setDirection(dir) {
        const container = document.querySelector('.dir-toggle-pill');
        const input = document.getElementById('dirInput');
        
        container.dataset.dir = dir;
        input.value = dir;
        
        if (dir === 'polishing_in') {
            document.getElementById('opt-out').classList.remove('active');
            document.getElementById('opt-in').classList.add('active');
        } else {
            document.getElementById('opt-in').classList.remove('active');
            document.getElementById('opt-out').classList.add('active');
        }
        recalculateAllRows();
    }

    function quickReceivePolishing(data) {
        // 1. Smooth Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // 2. Set direction to RECEIVE
        setDirection('polishing_in');

        // 3. Clear container & Add exactly one fresh item row
        const container = document.getElementById('items-container');
        container.innerHTML = '';
        
        // Reset the dynamic TomSelect instances map
        Object.keys(rowTomSelects).forEach(id => {
            delete rowTomSelects[id];
        });
        
        rowCount = 0;
        addItemRow(); // This creates row with id 0

        // 4. Set Worker
        if (workerTS) {
            workerTS.setValue(data.worker_id);
        }

        // 5. Select Item on row 0
        const ts = rowTomSelects[0];
        if (ts) {
            const item_id_str = data.item_id.toString();
            let originalOpt = itemsMaster.find(item => item.id.toString() === item_id_str);
            if (!originalOpt && data.item_name) {
                originalOpt = {
                    id: item_id_str,
                    name: data.item_name,
                    code: data.item_name.split(' - ')[0] || data.item_name,
                    is_set: data.item_name.includes('[SET]'),
                    components: []
                };
            }
            if (originalOpt) {
                if (!ts.options[item_id_str]) {
                    ts.addOption({
                        value: item_id_str,
                        text: (originalOpt.is_set ? '📦 [SET] ' : '🧩 [SINGLE] ') + originalOpt.code + ' - ' + originalOpt.name
                    });
                }
            }
            ts.setValue(item_id_str);
        }

        // 6. Convert pieces to lots if applicable
        const item = itemsMaster.find(it => it.id.toString() === data.item_id.toString());
        if (item) {
            const lotSize = item.lot_size || 1;
            const row = document.getElementById('row-0');
            if (row) {
                const lotsInput = row.querySelector('[name="lots[]"]');
                const manualInput = row.querySelector('[name="manual[]"]');
                
                if (lotsInput && manualInput) {
                    const lots = Math.floor(data.qty / lotSize);
                    const remainder = data.qty % lotSize;
                    lotsInput.value = lots;
                    manualInput.value = remainder;
                } else if (lotsInput) {
                    lotsInput.value = Math.ceil(data.qty / lotSize);
                }
            }
        }

        calculateRow(0);

        // 7. Directly save/submit the transaction!
        const form = document.getElementById('polishingForm');
        if (form) {
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.click();
                } else {
                    form.submit();
                }
            }
        }
    }
    window.quickReceivePolishing = quickReceivePolishing;

    function editPolishingTransaction(data) {
        // 1. Smooth Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // 2. Set direction
        setDirection(data.type);

        // 3. Set edit_id value
        document.getElementById('editIdInput').value = data.id;

        // 3b. Set Transaction Date if provided
        if (data.date) {
            if (entryDatePicker) {
                entryDatePicker.setDate(data.date);
                if (entryDatePicker.selectedDates[0]) {
                    updateTxDateBadge(entryDatePicker.selectedDates[0]);
                }
            }
            document.getElementById('polishing-date-form-input').value = data.date;
        }

        // 4. Clear container & Add exactly one fresh item row
        const container = document.getElementById('items-container');
        container.innerHTML = '';
        
        // Reset the dynamic TomSelect instances map
        Object.keys(rowTomSelects).forEach(id => {
            delete rowTomSelects[id];
        });
        
        rowCount = 0;
        addItemRow(); // This creates row with id 0

        // 5. Set Worker
        if (workerTS) {
            workerTS.setValue(data.worker_id);
        }

        // 6. Select Item on row 0
        const ts = rowTomSelects[0];
        if (ts) {
            const item_id_str = data.item_id.toString();
            let originalOpt = itemsMaster.find(item => item.id.toString() === item_id_str);
            if (!originalOpt && data.item_name) {
                originalOpt = {
                    id: item_id_str,
                    name: data.item_name,
                    code: data.item_name.split(' - ')[0] || data.item_name,
                    is_set: data.item_name.includes('[SET]'),
                    components: []
                };
            }
            if (originalOpt) {
                if (!ts.options[item_id_str]) {
                    ts.addOption({
                        value: item_id_str,
                        text: (originalOpt.is_set ? '📦 [SET] ' : '🧩 [SINGLE] ') + originalOpt.code + ' - ' + originalOpt.name
                    });
                }
            }
            ts.setValue(item_id_str);
        }

        // 7. Set lots, manual pieces and weight
        const item = itemsMaster.find(it => it.id.toString() === data.item_id.toString());
        if (item) {
            const lotSize = item.lot_size || 1;
            const lots = Math.floor(data.qty / lotSize);
            const remainder = data.qty % lotSize;
            
            const row = document.getElementById('row-0');
            if (row) {
                const lotsInput = row.querySelector('[name="lots[]"]');
                if (lotsInput) lotsInput.value = lots;

                const manualInput = row.querySelector('[name="manual[]"]');
                if (manualInput) manualInput.value = remainder;

                const weightInput = row.querySelector('[name="weight[]"]');
                if (weightInput) weightInput.value = data.weight;
            }
        }

        calculateRow(0);

        // 8. Update button text & insert cancel button if not present
        const submitBtn = document.querySelector('#polishingForm button[type="submit"]');
        if (submitBtn) {
            submitBtn.textContent = 'UPDATE TRANSACTION';
            submitBtn.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
            submitBtn.style.boxShadow = '0 0 15px rgba(245, 158, 11, 0.4)';
        }

        let cancelBtn = document.getElementById('cancelEditBtn');
        if (!cancelBtn) {
            cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.id = 'cancelEditBtn';
            cancelBtn.className = 'btn-secondary';
            cancelBtn.textContent = 'CANCEL EDIT';
            cancelBtn.style.marginTop = '8px';
            cancelBtn.style.background = 'rgba(239, 68, 68, 0.1)';
            cancelBtn.style.color = '#ef4444';
            cancelBtn.style.border = '1px solid rgba(239, 68, 68, 0.2)';
            cancelBtn.onclick = clearPolishingEdit;
            submitBtn.parentNode.insertBefore(cancelBtn, submitBtn.nextSibling);
        }
    }
    window.editPolishingTransaction = editPolishingTransaction;

    function clearPolishingEdit() {
        document.getElementById('editIdInput').value = '';

        if (entryDatePicker) {
            entryDatePicker.setDate(currentDate);
            if (entryDatePicker.selectedDates[0]) {
                updateTxDateBadge(entryDatePicker.selectedDates[0]);
            }
        }
        document.getElementById('polishing-date-form-input').value = currentDate;
        
        const submitBtn = document.querySelector('#polishingForm button[type="submit"]');
        if (submitBtn) {
            submitBtn.textContent = 'SAVE TRANSACTION';
            submitBtn.style.background = '';
            submitBtn.style.boxShadow = '';
        }

        const cancelBtn = document.getElementById('cancelEditBtn');
        if (cancelBtn) {
            cancelBtn.remove();
        }

        // Reset inputs
        const container = document.getElementById('items-container');
        container.innerHTML = '';
        Object.keys(rowTomSelects).forEach(id => {
            delete rowTomSelects[id];
        });
        rowCount = 0;
        addItemRow();

        if (workerTS) {
            workerTS.clear();
        }
    }
    window.clearPolishingEdit = clearPolishingEdit;

    function updateTxDateBadge(dateObj) {
        if (!dateObj) return;
        const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
        const monthEl = document.getElementById("tx-date-badge-month");
        const dayEl = document.getElementById("tx-date-badge-day");
        if (monthEl && dayEl) {
            monthEl.textContent = months[dateObj.getMonth()];
            dayEl.textContent = dateObj.getDate();
        }
    }

    let currentDate = '{{ selected_date }}';
    let entryDatePicker = null;

    document.addEventListener("DOMContentLoaded", () => {
        // Initialize Datepicker
        flatpickr("#polishing-date-picker", {
            altInput: true,
            altFormat: "F j, Y",
            dateFormat: "Y-m-d",
            defaultDate: currentDate,
            theme: "dark",
            onChange: function(selectedDates, dateStr, instance) {
                window.location.href = `?date=${dateStr}`;
            }
        });

        entryDatePicker = flatpickr("#tx-date-picker-input", {
            altInput: true,
            altInputClass: "tx-date-picker-alt-input",
            altFormat: "j/n/Y",
            dateFormat: "Y-m-d",
            defaultDate: currentDate,
            theme: "dark",
            onReady: function(selectedDates, dateStr, instance) {
                if (instance.altInput) {
                    instance.altInput.style.setProperty("padding-left", "62px", "important");
                }
            },
            onChange: function(selectedDates, dateStr, instance) {
                document.getElementById('polishing-date-form-input').value = dateStr;
                if (selectedDates[0]) {
                    updateTxDateBadge(selectedDates[0]);
                }
            }
        });
        document.getElementById('polishing-date-form-input').value = currentDate;
        if (entryDatePicker && entryDatePicker.selectedDates[0]) {
            updateTxDateBadge(entryDatePicker.selectedDates[0]);
        }

        addItemRow(); // Start with one row

        workerTS = new TomSelect("#workerSelect", {
            create: false,
            placeholder: 'Select Worker',
            render: {
                option: function (data, escape) {
                    const id = data.id || data.value || '';
                    const text = data.text || '';
                    const isExternal = id.startsWith('jw_');
                    
                    let iconHtml = '<span style="margin-right:8px;font-size:14px;">🏠</span>';
                    if (isExternal) {
                        iconHtml = `<img src="/static/img/logo.jpg" 
                                     style="width:20px;height:20px;border-radius:4px;margin-right:8px;vertical-align:middle;object-fit:cover;border:1px solid rgba(255,255,255,0.1);" 
                                     onerror="this.style.display='none'; this.nextSibling.style.display='inline';"
                                     ><span style="display:none;margin-right:8px;font-size:14px;">⚙️</span>`;
                    }
                    
                    return `<div style="display:flex;align-items:center;padding:3px 0;">
                                ${iconHtml}
                                <span style="font-size:13px;font-weight:600;">${escape(text)}</span>
                            </div>`;
                },
                item: function (data, escape) {
                    const id = data.id || data.value || '';
                    const text = data.text || '';
                    const isExternal = id.startsWith('jw_');
                    
                    let iconHtml = '<span style="margin-right:8px;font-size:14px;">🏠</span>';
                    if (isExternal) {
                        iconHtml = `<img src="/static/img/logo.jpg" 
                                     style="width:20px;height:20px;border-radius:4px;margin-right:8px;vertical-align:middle;object-fit:cover;" 
                                     onerror="this.style.display='none'; this.nextSibling.style.display='inline';"
                                     ><span style="display:none;margin-right:8px;font-size:14px;">⚙️</span>`;
                    }
                    
                    return `<div style="display:flex;align-items:center;">
                                ${iconHtml}
                                <span style="font-size:13px;font-weight:700;color:var(--text-primary);">${escape(text)}</span>
                            </div>`;
                }
            }
        });

        originalWorkers = Object.values(workerTS.options).map(opt => ({
            id: opt.value,
            name: opt.text,
            value: opt.value,
            text: opt.text
        }));

        // Auto-select allocated item when a worker is chosen
        workerTS.on('change', function(val) {
            const control = document.querySelector('#workerSelect').nextElementSibling;
            if (control) {
                control.style.border = '';
                control.style.boxShadow = '';
            }
            if (!val) {
                lastAllocatedItemId = null;
                filterPolishingItemsByWorker('');
                recalculateAllRows();
                return;
            }
            
            filterPolishingItemsByWorker(val);
            
            if (!isAutoSelectingWorker) {
                const alloc = allocationsMaster.find(a => {
                    if (a.worker_id === val) {
                        const optExists = document.querySelector(`#workerSelect option[value="${a.worker_id}"]`);
                        return !!optExists;
                    }
                    return false;
                });
                if (alloc) {
                    let itemId = alloc.item_id;

                    // Parent Set Lookup: If the allocated item is a component of a SET, prefer selecting that SET in Polishing!
                    const parentSet = itemsMaster.find(it => it.is_set && it.components && it.components.some(c => c.id == itemId));
                    if (parentSet) {
                        itemId = parentSet.id;
                    }

                    lastAllocatedItemId = itemId;
                    // Auto-fill empty rows with this item
                    Object.keys(rowTomSelects).forEach(id => {
                        const ts = rowTomSelects[id];
                        if (ts && !ts.getValue()) {
                            ts.setValue(itemId);
                        }
                    });
                } else {
                    lastAllocatedItemId = null;
                }
            }
            recalculateAllRows();
        });

        document.getElementById('polishingForm').addEventListener('submit', function(e) {
            // 1. Validate Assigned Worker
            const workerVal = workerTS.getValue();
            if (!workerVal) {
                e.preventDefault();
                const control = document.querySelector('#workerSelect').nextElementSibling;
                if (control) {
                    control.style.border = '2px solid #ef4444';
                    control.style.boxShadow = '0 0 0 3px rgba(239, 68, 68, 0.2)';
                    control.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                alert("Please select an Assigned Worker before saving polishing entries.");
                return;
            }

            // 2. Validate Row Selection
            let hasEmptyRow = false;
            document.querySelectorAll('.item-row').forEach(row => {
                const id = row.id.replace('row-', '');
                const select = row.querySelector('.item-select');
                if (select && !select.value) {
                    hasEmptyRow = true;
                    const control = select.nextElementSibling;
                    if (control) {
                        control.style.border = '2px solid #ef4444';
                        control.style.boxShadow = '0 0 0 3px rgba(239, 68, 68, 0.2)';
                        control.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            });

            if (hasEmptyRow) {
                e.preventDefault();
                alert("Please select an item for all transaction rows.");
                return;
            }

            const rowsData = [];
            
            document.querySelectorAll('.item-row').forEach(row => {
                const id = row.id.replace('row-', '');
                const select = row.querySelector('.item-select');
                const itemId = select.value;
                if (!itemId) return;
                
                const packaging = document.getElementById(`pkg-input-${id}`).value;
                const lots = parseInt(row.querySelector('[name="lots[]"]').value || 0);
                const manual = parseInt(row.querySelector('[name="manual[]"]').value || 0);
                const weight = parseFloat(row.querySelector('[name="weight[]"]').value || 0);
                
                const rowObj = {
                    item_id: itemId,
                    packaging: packaging,
                    lots: lots,
                    manual: manual,
                    weight: weight
                };
                
                const item = itemsMaster.find(it => it.id == itemId);
                if (item && item.is_set) {
                    rowObj.components = [];
                    row.querySelectorAll('.comp-row-override').forEach(compRow => {
                        const compId = compRow.dataset.compId;
                        const qtyPerSet = parseInt(compRow.dataset.qtyPerSet);
                        const extraInput = compRow.querySelector('.comp-extra-input');
                        const extraQty = parseInt(extraInput.value || 0);
                        
                        const setLotSize = (packaging === 'box' ? (item.lot_with_box && item.lot_with_box > 0 ? item.lot_with_box : item.lot_size) : item.lot_size) || 1;
                        const setTotalQty = (lots * setLotSize) + manual;
                        const totalQty = (qtyPerSet * setTotalQty) + extraQty;
                        
                        rowObj.components.push({
                            component_id: compId,
                            qty_per_set: qtyPerSet,
                            extra_qty: extraQty,
                            total_qty: totalQty
                        });
                    });
                }
                
                rowsData.push(rowObj);
            });
            
            if (rowsData.length === 0) {
                alert("Please add at least one item transaction.");
                e.preventDefault();
                return;
            }
            
            document.getElementById('transaction-data-input').value = JSON.stringify(rowsData);
        });

        // Collapsible WIP Accordion Heuristic & Event Listeners
        const wipHeaders = document.querySelectorAll('.wip-worker-header');
        const wipRows = document.querySelectorAll('.wip-worker-row');
        
        if (wipHeaders.length > 0) {
            const totalWipRows = wipRows.length;
            const defaultCollapse = totalWipRows > 10;
            
            wipHeaders.forEach(header => {
                const targetClass = header.getAttribute('data-target');
                const icon = header.querySelector('.wip-toggle-icon');
                
                if (defaultCollapse) {
                    document.querySelectorAll('.' + targetClass).forEach(row => row.style.display = 'none');
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                } else {
                    document.querySelectorAll('.' + targetClass).forEach(row => row.style.display = '');
                    if (icon) icon.style.transform = 'rotate(0deg)';
                }
                
                header.addEventListener('click', () => {
                    const rows = document.querySelectorAll('.' + targetClass);
                    const isCollapsed = rows.length > 0 && rows[0].style.display === 'none';
                    
                    rows.forEach(row => {
                        row.style.display = isCollapsed ? '' : 'none';
                    });
                    
                    if (icon) {
                        icon.style.transform = isCollapsed ? 'rotate(0deg)' : 'rotate(-90deg)';
                    }
                });
            });
        }
        // Handle URL parameters for autofill (item_code, direction)
        const urlParams = new URLSearchParams(window.location.search);
        const itemCode = urlParams.get('item_code');
        const direction = urlParams.get('direction');
        const tab = urlParams.get('tab');
        
        if (itemCode && tab !== 'stock') {
            // Set direction first if present
            if (direction) {
                const container = document.querySelector('.dir-toggle-pill');
                if (container && container.dataset.dir !== direction) {
                    toggleDirection();
                }
            }
            
            // Find item by code in itemsMaster
            const matchedItem = itemsMaster.find(it => it.code.toLowerCase().trim() === itemCode.toLowerCase().trim());
            if (matchedItem) {
                const firstRowId = Object.keys(rowTomSelects)[0];
                const ts = rowTomSelects[firstRowId];
                
                // Check if only one worker has pending WIP for this item
                const matchingKeys = Object.keys(workerWIPByItem).filter(key => key.endsWith('_' + matchedItem.id));
                if (matchingKeys.length === 1) {
                    const workerId = matchingKeys[0].split('_').slice(0, 2).join('_');
                    const pendingQty = workerWIPByItem[matchingKeys[0]];
                    
                    // Auto-select worker FIRST
                    if (workerTS) {
                        workerTS.setValue(workerId);
                    }
                    
                    // Auto-select item SECOND
                    if (ts) {
                        ts.setValue(matchedItem.id.toString());
                    }
                    
                    // Auto-fill quantity THIRD
                    setTimeout(() => {
                        const row = document.getElementById(`row-${firstRowId}`);
                        if (row) {
                            const manualInput = row.querySelector('[name="manual[]"]');
                            if (manualInput) {
                                manualInput.value = pendingQty;
                                calculateRow(firstRowId);
                            }
                        }
                    }, 250);
                } else {
                    // No single worker, just select the item
                    if (ts) {
                        ts.setValue(matchedItem.id.toString());
                    }
                }
            }
        }

        if (tab) {
            switchMainTab(tab);
        }
    });

    let markInClickTimer = null;
    function handleMarkInClick(event, url, itemName, maxQty) {
        event.preventDefault();
        let targetUrl = url;
        if (typeof currentDate !== 'undefined' && currentDate) {
            targetUrl += `&date=${currentDate}`;
        }
        
        if (event.detail === 2) {
            // Double click detected! Clear single-click timer and show the modal
            if (markInClickTimer) {
                clearTimeout(markInClickTimer);
                markInClickTimer = null;
            }
            openMarkInRejectionModal(targetUrl, itemName, maxQty);
        } else if (event.detail === 1) {
            // Single click - set timer to redirect in 250ms unless a second click arrives
            markInClickTimer = setTimeout(() => {
                window.location.href = targetUrl;
            }, 250);
        }
    }

    function openMarkInRejectionModal(targetUrl, itemName, maxQty) {
        document.getElementById('rejectionModalTargetUrl').value = targetUrl;
        document.getElementById('rejectionModalTitle').textContent = `Rejections for ${itemName}`;
        document.getElementById('rejectionPcsInput').value = '0';
        document.getElementById('rejectionPcsInput').max = maxQty;
        document.getElementById('rejectionModalSubtitle').innerHTML = `Enter Defective/Rejected pieces found in this lot.<br><span style="color:var(--accent-gold); font-weight:700;">Max Available Qty: ${maxQty} pcs</span>`;
        
        const modal = document.getElementById('markInRejectionModal');
        modal.style.display = 'flex';
        setTimeout(() => {
            document.getElementById('rejectionPcsInput').focus();
        }, 50);
    }

    function closeMarkInRejectionModal() {
        document.getElementById('markInRejectionModal').style.display = 'none';
    }

    function submitRejectionModal(event) {
        event.preventDefault();
        const targetUrl = document.getElementById('rejectionModalTargetUrl').value;
        const rejections = parseInt(document.getElementById('rejectionPcsInput').value || 0);
        
        const separator = targetUrl.includes('?') ? '&' : '?';
        window.location.href = `${targetUrl}${separator}rejections=${rejections}`;
    }
