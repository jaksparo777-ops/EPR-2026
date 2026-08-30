
    // Adjustment Drawer controls
    let activeAdjustmentMode = 'single';

    function setAdjustmentMode(mode) {
        activeAdjustmentMode = mode;
        const btnSingle = document.getElementById('btn-adj-single');
        const btnBulk = document.getElementById('btn-adj-bulk');
        const singleFields = document.getElementById('single-mode-fields');
        const bulkFields = document.getElementById('bulk-mode-fields');

        if (mode === 'single') {
            btnSingle.style.background = 'var(--accent-blue)';
            btnSingle.style.color = 'white';
            btnBulk.style.background = 'transparent';
            btnBulk.style.color = 'var(--text-secondary)';
            singleFields.style.display = 'flex';
            bulkFields.style.display = 'none';
            
            document.getElementById('adj_item').disabled = false;
            document.getElementById('adj_physical_count').disabled = false;
            document.querySelectorAll('.bulk-input-field').forEach(input => input.disabled = true);
        } else {
            btnSingle.style.background = 'transparent';
            btnSingle.style.color = 'var(--text-secondary)';
            btnBulk.style.background = 'var(--accent-blue)';
            btnBulk.style.color = 'white';
            singleFields.style.display = 'none';
            bulkFields.style.display = 'flex';
            
            document.getElementById('adj_item').disabled = true;
            document.getElementById('adj_physical_count').disabled = true;
            
            document.querySelectorAll('.bulk-input-field').forEach(input => {
                if (input.name === 'physical_count') {
                    input.disabled = false;
                } else {
                    input.disabled = true;
                }
            });

            fetchAllCurrentStock();
        }
    }

    function openAdjustmentDrawer() {
        document.getElementById('adjustmentBackdrop').style.display = 'block';
        document.getElementById('adjustmentDrawer').style.right = '0';
        
        if (!window.adjItemTS && document.getElementById('adj_item')) {
            window.adjItemTS = new TomSelect('#adj_item', {
                create: false,
                placeholder: 'Choose Item to Adjust'
            });
        }
        if (!window.bulkItemTS && document.getElementById('bulk_item_selector')) {
            window.bulkItemTS = new TomSelect('#bulk_item_selector', {
                create: false,
                placeholder: 'Type/Search Item to Add...'
            });
        }
        setAdjustmentMode('single');
    }

    function closeAdjustmentDrawer() {
        document.getElementById('adjustmentBackdrop').style.display = 'none';
        document.getElementById('adjustmentDrawer').style.right = '-650px';
        document.getElementById('adjustmentForm').reset();
        document.getElementById('adj_current_qty').innerText = '--';
        document.getElementById('adj_delta_info').style.display = 'none';
        if (window.adjItemTS) {
            window.adjItemTS.clear();
        }
        clearBulkInputs();
        setAdjustmentMode('single');
    }

    function onWarehouseChange() {
        if (activeAdjustmentMode === 'single') {
            fetchCurrentStock();
        } else {
            fetchAllCurrentStock();
        }
    }

    function fetchCurrentStock() {
        const itemId = document.getElementById('adj_item').value;
        const warehouse = document.getElementById('adj_warehouse').value;
        const currentQtyEl = document.getElementById('adj_current_qty');

        if (!itemId || !warehouse) {
            currentQtyEl.innerText = '--';
            return;
        }

        currentQtyEl.innerText = 'Calculating...';

        fetch(`/api/stock/get-qty/?item_id=${itemId}&warehouse=${warehouse}`)
            .then(res => res.json())
            .then(data => {
                if (data.qty !== undefined) {
                    currentQtyEl.innerText = data.qty;
                    recalculateDelta();
                } else {
                    currentQtyEl.innerText = 'Error';
                }
            })
            .catch(() => {
                currentQtyEl.innerText = 'Error';
            });
    }

    function fetchAllCurrentStock() {
        const warehouse = document.getElementById('adj_warehouse').value;
        document.querySelectorAll('.bulk-curr-val').forEach(span => span.innerText = '...');
        
        fetch(`/api/stock/get-all-qty/?warehouse=${warehouse}`)
            .then(res => res.json())
            .then(data => {
                if (data.qtys) {
                    for (const [itemId, qty] of Object.entries(data.qtys)) {
                        const el = document.getElementById(`bulk_curr_${itemId}`);
                        if (el) el.innerText = qty;
                    }
                }
            })
            .catch(() => {
                document.querySelectorAll('.bulk-curr-val').forEach(span => span.innerText = 'Error');
            });
    }

    function showBulkRow(itemId) {
        if (!itemId) return;
        const row = document.getElementById(`bulk-row-${itemId}`);
        if (row) {
            row.style.display = 'flex';
            document.getElementById('bulk_item_selector').value = '';
            if (window.bulkItemTS) {
                window.bulkItemTS.clear(true);
            }
        }
    }

    function hideBulkRow(itemId) {
        const row = document.getElementById(`bulk-row-${itemId}`);
        if (row) {
            row.style.display = 'none';
            const numInput = row.querySelector('.bulk-phys-count');
            if (numInput) numInput.value = '';
            const hiddenInput = row.querySelector('.bulk-hidden-item-id');
            if (hiddenInput) hiddenInput.disabled = true;
        }
    }

    function selectAllBulkRows() {
        document.querySelectorAll('.bulk-item-row').forEach(row => {
            row.style.display = 'flex';
        });
    }

    function applyDefaultQtyToAll() {
        const qtyVal = document.getElementById('bulk_default_qty').value;
        if (qtyVal.trim() === '') {
            alert('Please enter a default quantity first.');
            return;
        }
        
        selectAllBulkRows();
        
        document.querySelectorAll('.bulk-phys-count').forEach(input => {
            input.value = qtyVal;
            const row = input.closest('.bulk-item-row');
            if (row) {
                const itemId = row.getAttribute('data-item-id');
                onBulkInput(input, itemId);
            }
        });
    }

    function onBulkInput(inputEl, itemId) {
        const row = inputEl.closest('.bulk-item-row');
        const hiddenItemIdInput = row.querySelector('.bulk-hidden-item-id');
        
        if (inputEl.value.trim() !== '') {
            hiddenItemIdInput.disabled = false;
        } else {
            hiddenItemIdInput.disabled = true;
        }
    }

    function clearBulkInputs() {
        const defQtyInput = document.getElementById('bulk_default_qty');
        if (defQtyInput) defQtyInput.value = '';
        
        document.querySelectorAll('.bulk-input-field').forEach(input => {
            if (input.type === 'number') {
                input.value = '';
            }
            if (input.type === 'hidden') {
                input.disabled = true;
            }
        });
        document.querySelectorAll('.bulk-item-row').forEach(row => {
            row.style.display = 'none';
        });
        if (window.bulkItemTS) {
            window.bulkItemTS.clear(true);
        }
    }

    function recalculateDelta() {
        const currentText = document.getElementById('adj_current_qty').innerText;
        const currentQty = parseInt(currentText);
        const physicalQty = parseInt(document.getElementById('adj_physical_count').value);
        const deltaInfo = document.getElementById('adj_delta_info');
        const deltaPcs = document.getElementById('adj_delta_pcs');

        if (isNaN(currentQty) || isNaN(physicalQty)) {
            deltaInfo.style.display = 'none';
            return;
        }

        const delta = physicalQty - currentQty;
        deltaPcs.innerText = (delta > 0 ? '+' : '') + delta;
        
        if (delta > 0) {
            deltaPcs.style.color = '#34d399';
        } else if (delta < 0) {
            deltaPcs.style.color = '#ef4444';
        } else {
            deltaPcs.style.color = '#94a3b8';
        }
        
        deltaInfo.style.display = 'block';
    }

    // Ajax Form Submission Handler
    document.getElementById('adjustmentForm').addEventListener('submit', function(e) {
        e.preventDefault();

        const submitBtn = document.getElementById('btnSubmitAdjustment');
        const originalBtnHTML = submitBtn.innerHTML;

        submitBtn.disabled = true;
        submitBtn.innerHTML = '⚡ Processing Audit Correction...';

        if (activeAdjustmentMode === 'single') {
            const itemId = document.getElementById('adj_item').value;
            const physicalCount = document.getElementById('adj_physical_count').value;
            if (!itemId || physicalCount === '') {
                alert('Please select an item and enter actual count.');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnHTML;
                return;
            }
        } else {
            let hasAnyBulkValue = false;
            document.querySelectorAll('#bulk-adjust-list input[type="number"]').forEach(input => {
                if (input.value.trim() !== '') {
                    hasAnyBulkValue = true;
                }
            });
            if (!hasAnyBulkValue) {
                alert('Please enter actual physical count for at least one item.');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnHTML;
                return;
            }
        }

        const formData = new FormData(this);

        fetch('/api/stock/adjust/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                const container = document.querySelector('.toast-container') || (() => {
                    const c = document.createElement('div');
                    c.className = 'toast-container';
                    document.querySelector('.content').appendChild(c);
                    return c;
                })();

                const toast = document.createElement('div');
                toast.className = 'toast toast-success';
                toast.role = 'alert';
                toast.innerHTML = `<span>${data.message}</span><button type="button" class="toast-close" onclick="this.parentElement.remove()">&times;</button>`;
                container.appendChild(toast);

                setTimeout(() => {
                    toast.style.opacity = 0;
                    setTimeout(() => toast.remove(), 300);
                }, 5000);

                closeAdjustmentDrawer();
                
                setTimeout(() => {
                    location.reload();
                }, 1000);

            } else {
                alert('Correction Failed: ' + (data.error || 'Unknown error occurred.'));
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnHTML;
            }
        })
        .catch(err => {
            alert('A networking error occurred during adjustment.');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHTML;
        });
    });
