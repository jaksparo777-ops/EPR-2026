
    let searchDebounceTimeout;

    function openGlobalSearch() {
        const overlay = document.getElementById('globalSearchOverlay');
        overlay.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Lock background scroll
        setTimeout(() => {
            document.getElementById('globalSearchInput').focus();
        }, 50);
    }

    function closeGlobalSearch() {
        document.getElementById('globalSearchOverlay').style.display = 'none';
        document.body.style.overflow = ''; // Unlock background scroll
        document.getElementById('globalSearchInput').value = '';
        document.getElementById('globalSearchResults').innerHTML = `
            <div style="text-align:center; color:var(--text-secondary); padding:20px 0; font-size:13.5px;">
                Type at least 2 characters to search for items, POs, or pages...
            </div>
        `;
    }

    // Close on click outside search card
    const globalOverlay = document.getElementById('globalSearchOverlay');
    if (globalOverlay) {
        globalOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeGlobalSearch();
            }
        });
    }

    // Keyboard shortcuts listener
    window.addEventListener('keydown', function(e) {
        // Ctrl + K or Cmd + K
        const isK = e.key && (e.key.toLowerCase() === 'k' || e.code === 'KeyK');
        if ((e.ctrlKey || e.metaKey) && isK) {
            e.preventDefault();
            openGlobalSearch();
        }
        // Escape key to close
        if (e.key === 'Escape') {
            const overlay = document.getElementById('globalSearchOverlay');
            if (overlay && overlay.style.display === 'flex') {
                closeGlobalSearch();
            }
        }
    });

    function triggerGlobalSearch() {
        clearTimeout(searchDebounceTimeout);
        const query = document.getElementById('globalSearchInput').value.trim();
        if (query.length < 2) {
            document.getElementById('globalSearchResults').innerHTML = `
                <div style="text-align:center; color:var(--text-secondary); padding:20px 0; font-size:13.5px;">
                    Type at least 2 characters to search for items, POs, or pages...
                </div>
            `;
            return;
        }

        document.getElementById('globalSearchResults').innerHTML = `
            <div style="text-align:center; color:var(--text-secondary); padding:20px 0; font-size:13.5px;">
                🔍 Searching database...
            </div>
        `;

        searchDebounceTimeout = setTimeout(() => {
            fetch(`/api/global-search/?q=${encodeURIComponent(query)}`)
                .then(res => res.json())
                .then(data => {
                    renderSearchResults(data.results);
                })
                .catch(err => {
                    console.error("Global search error:", err);
                    document.getElementById('globalSearchResults').innerHTML = `
                        <div style="text-align:center; color:#f87171; padding:20px 0; font-size:13.5px;">
                            ⚠️ Error: ${err.message || err}
                        </div>
                    `;
                });
        }, 200);
    }

    function renderSearchResults(results) {
        const container = document.getElementById('globalSearchResults');
        container.innerHTML = '';

        let hasResults = false;

        // A. NAVIGATION RESULTS
        if (results.navigation && results.navigation.length > 0) {
            hasResults = true;
            const navSec = document.createElement('div');
            navSec.innerHTML = `<div class="search-section-title">🚀 QUICK PAGES</div>`;
            const list = document.createElement('div');
            list.style.display = 'grid';
            list.style.gridTemplateColumns = 'repeat(auto-fit, minmax(220px, 1fr))';
            list.style.gap = '10px';
            
            results.navigation.forEach(page => {
                list.innerHTML += `
                    <a href="${page.url}" class="search-nav-item">
                        ${page.title}
                    </a>
                `;
            });
            navSec.appendChild(list);
            container.appendChild(navSec);
        }

        // B. ITEMS / SKU RESULTS WITH PRODUCTION PIPELINE
        if (results.items && results.items.length > 0) {
            hasResults = true;
            const itemSec = document.createElement('div');
            itemSec.innerHTML = `<div class="search-section-title">📦 SKU PRODUCTION LIFECYCLES</div>`;
            const list = document.createElement('div');
            list.style.display = 'flex';
            list.style.flexDirection = 'column';
            list.style.gap = '16px';

            results.items.forEach(item => {
                const isSet = item.item_type === 'SET';
                const escCode = encodeURIComponent(item.code);
                
                // Casting always routes to Company 1 (NC)
                const castingUrl = `/select-company/?company_id=1&next=${encodeURIComponent('/casting/?tab=entry&item_code=' + item.code)}`;
                
                // All downstream stages (Machining, Polishing, Packaging, Spares, Cartons, Orders) always route to Company 2 (OM)
                const machOutUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/machining/?item_code=' + item.code + '&direction=machining_out')}`;
                const machInUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/machining/?item_code=' + item.code + '&direction=machining_in')}`;
                const machStkUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/machining/?tab=stock&item_code=' + item.code)}`;
                const polOutUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/polishing/?item_code=' + item.code + '&direction=polishing_out')}`;
                const polInUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/polishing/?item_code=' + item.code + '&direction=polishing_in')}`;
                const bufferUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/packaging/?tab=spares&item_code=' + item.code)}`;
                const packQUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/packaging/?tab=entry&item_code=' + item.code)}`;
                const readyUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/packaging/?tab=cartons&search=' + item.code)}`;
                const demandUrl = `/select-company/?company_id=2&next=${encodeURIComponent('/orders/?item_code=' + item.code)}`;

                const activeCompanyId = "";
                const isCastingUnclickable = activeCompanyId === '2';
                
                let castingHtml = '';
                if (isCastingUnclickable) {
                    castingHtml = `
                        <div class="pipeline-step unclickable">
                            <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">CASTING</span>
                            <span style="font-size:14px; font-weight:800; color:#f59e0b; margin-top:4px;">${item.casting_avail}</span>
                        </div>
                    `;
                } else {
                    const castingClass = (!item.casting_required || isSet) ? 'disabled' : '';
                    castingHtml = `
                        <a href="${castingUrl}" class="pipeline-step ${castingClass}">
                            <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">CASTING</span>
                            <span style="font-size:14px; font-weight:800; color:#f59e0b; margin-top:4px;">${item.casting_avail}</span>
                        </a>
                    `;
                }

                const machDisabled = (!item.machining_required || isSet) ? 'disabled' : '';
                const polDisabled = (!item.polishing_required) ? 'disabled' : '';

                list.innerHTML += `
                    <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:12px; padding:16px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
                            <div>
                                <strong style="font-size:16px; color:var(--accent-blue);">${item.code}</strong>
                                <span style="font-size:13px; color:var(--text-secondary); margin-left:8px;">${item.name}</span>
                            </div>
                            <a href="${demandUrl}" style="font-size:11px; font-weight:800; background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 10px; border-radius:6px; text-decoration:none; cursor:pointer; transition:all 0.2s;" onmouseover="this.style.background='rgba(239,68,68,0.25)'" onmouseout="this.style.background='rgba(239,68,68,0.15)'">
                                PO Demand: ${item.demand} pcs
                            </a>
                        </div>
                        
                        <!-- Supply Chain Pipeline Stepper -->
                        <div style="display:flex; gap:8px; overflow-x:auto; padding-bottom:4px; margin-top:8px;">
                            ${castingHtml}
                            <a href="${machOutUrl}" class="pipeline-step ${machDisabled}" title="Issue raw castings to machining worker">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">MACH OUT</span>
                                <span style="font-size:12px; font-weight:800; color:#60a5fa; margin-top:4px;">📤 Issue</span>
                            </a>
                            <a href="${machInUrl}" class="pipeline-step ${machDisabled}" title="Receive machined goods from worker (WIP: ${item.machining_wip} pcs)">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">MACH IN</span>
                                <span style="font-size:13px; font-weight:800; color:#3b82f6; margin-top:4px;">📥 ${item.machining_wip}</span>
                            </a>
                            <a href="${machStkUrl}" class="pipeline-step ${machDisabled}">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">MACH STK</span>
                                <span style="font-size:14px; font-weight:800; color:#10b981; margin-top:4px;">${item.machining_avail}</span>
                            </a>
                            <a href="${polOutUrl}" class="pipeline-step ${polDisabled}" title="Issue machined items to polishing worker">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">POL OUT</span>
                                <span style="font-size:12px; font-weight:800; color:#fbbf24; margin-top:4px;">📤 Issue</span>
                            </a>
                            <a href="${polInUrl}" class="pipeline-step ${polDisabled}" title="Receive polished goods from worker (WIP: ${item.polishing_wip} pcs)">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">POL IN</span>
                                <span style="font-size:13px; font-weight:800; color:#8b5cf6; margin-top:4px;">📥 ${item.polishing_wip}</span>
                            </a>
                            <a href="${bufferUrl}" class="pipeline-step">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">BUFFER</span>
                                <span style="font-size:14px; font-weight:800; color:#ec4899; margin-top:4px;">${item.loose_buffer}</span>
                            </a>
                            <a href="${packQUrl}" class="pipeline-step">
                                <span style="font-size:9px; font-weight:800; color:var(--text-secondary);">PACK Q</span>
                                <span style="font-size:14px; font-weight:800; color:#f43f5e; margin-top:4px;">${item.packaging_queue}</span>
                            </a>
                            <a href="${readyUrl}" class="pipeline-step" style="border-color:rgba(16,185,129,0.35); background:rgba(16,185,129,0.05); min-width:85px; align-items:center;">
                                <span style="font-size:9px; font-weight:800; color:#10b981;">READY CTN</span>
                                <div style="margin-top:4px; display:flex; align-items:baseline; justify-content:center; gap:4px; width:100%;">
                                    <span style="font-size:20px; font-weight:900; color:#10b981; line-height:1;">${item.cartons_count}</span>
                                    <span style="font-size:11px; font-weight:600; color:#60a5fa; white-space:nowrap;">(${item.ready_stock} pcs)</span>
                                </div>
                            </a>
                        </div>
                    </div>
                `;
            });
            itemSec.appendChild(list);
            container.appendChild(itemSec);
        }

        // C. ORDERS RESULTS
        if (results.orders && results.orders.length > 0) {
            hasResults = true;
            const orderSec = document.createElement('div');
            orderSec.innerHTML = `<div class="search-section-title">📋 ACTIVE CUSTOMER ORDERS</div>`;
            const list = document.createElement('div');
            list.style.display = 'flex';
            list.style.flexDirection = 'column';
            list.style.gap = '8px';

            results.orders.forEach(order => {
                let statusColor = '#3b82f6';
                if (order.status === 'COMPLETED') statusColor = '#10b981';
                else if (order.status === 'PARTIAL') statusColor = '#f59e0b';
                
                list.innerHTML += `
                    <a href="/orders/?highlight=${order.id}" class="search-nav-item" style="justify-content:space-between;">
                        <div>
                            <strong style="color:var(--accent-blue);">${order.order_number}</strong>
                            <span style="margin-left:10px; color:var(--text-secondary); font-size:12.5px;">${order.client_name}</span>
                        </div>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span style="font-size:11px; font-weight:600; color:var(--text-secondary);">Promise: ${order.promised_date}</span>
                            <span style="background:${statusColor}22; color:${statusColor}; border:1px solid ${statusColor}44; padding:2px 8px; border-radius:6px; font-size:10px; font-weight:800; text-transform:uppercase;">${order.status}</span>
                        </div>
                    </a>
                `;
            });
            orderSec.appendChild(list);
            container.appendChild(orderSec);
        }

        // D. WORKERS / STAFF RESULTS
        if (results.workers && results.workers.length > 0) {
            hasResults = true;
            const workerSec = document.createElement('div');
            workerSec.innerHTML = `<div class="search-section-title">👥 STAFF & JOB WORKERS</div>`;
            const list = document.createElement('div');
            list.style.display = 'flex';
            list.style.flexDirection = 'column';
            list.style.gap = '8px';

            results.workers.forEach(w => {
                const targetId = w.type === 'Internal' ? `w_${w.id}` : `jw_${w.id}`;
                const reportUrl = w.type === 'Internal' 
                    ? `/worker/${w.id}/report/` 
                    : `/ledger/job-worker/${w.id}/report/`;
                
                const tabParam = w.type === 'Internal' ? 'staff' : 'jw';
                const ptypeParam = w.type === 'Internal' ? 'SALARY' : 'JOB_WORK';
                const profileUrl = `/ledger/?action=profile&target_id=${targetId}&tab=${tabParam}`;
                const paymentUrl = `/ledger/?action=payment&target_id=${targetId}&payment_type=${ptypeParam}&tab=${tabParam}`;
                
                list.innerHTML += `
                    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.04); border-radius:8px;">
                        <div>
                            <strong style="color:var(--accent-blue);">${w.name}</strong>
                            <span style="margin-left:10px; color:var(--text-secondary); font-size:12.5px;">${w.type} (${w.process || 'General'})</span>
                        </div>
                        <div style="display:flex; gap:8px;">
                            <a href="${reportUrl}" class="action-btn" style="text-decoration:none; display:inline-block; background:rgba(16,185,129,0.1); color:#10b981; border:1px solid rgba(16,185,129,0.2); font-weight:700; padding:4px 8px; font-size:11px; border-radius:6px; cursor:pointer;">
                                📋 Statement
                            </a>
                            <a href="${profileUrl}" class="action-btn" style="text-decoration:none; display:inline-block; background:rgba(59,130,246,0.1); color:#3b82f6; border:1px solid rgba(59,130,246,0.2); font-weight:700; padding:4px 8px; font-size:11px; border-radius:6px; cursor:pointer;">
                                👤 Profile
                            </a>
                            <a href="${paymentUrl}" class="action-btn" style="text-decoration:none; display:inline-block; background:rgba(245,158,11,0.1); color:#f59e0b; border:1px solid rgba(245,158,11,0.2); font-weight:700; padding:4px 8px; font-size:11px; border-radius:6px; cursor:pointer;">
                                💸 Pay / Loan
                            </a>
                        </div>
                    </div>
                `;
            });
            workerSec.appendChild(list);
            container.appendChild(workerSec);
        }

        if (!hasResults) {
            container.innerHTML = `
                <div style="text-align:center; color:var(--text-secondary); padding:20px 0; font-size:13.5px;">
                    😕 No matches found for "${document.getElementById('globalSearchInput').value.trim()}"
                </div>
            `;
        }
    }

    // Auto-select item on page load if ?item_code=XXX is in the URL
    window.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            const urlParams = new URLSearchParams(window.location.search);
            const itemCode = urlParams.get('item_code');
            if (itemCode) {
                const selects = document.querySelectorAll('select');
                selects.forEach(select => {
                    let foundVal = '';
                    const codeLower = itemCode.toLowerCase().trim();
                    for (let opt of select.options) {
                        const optText = opt.text.toLowerCase().trim();
                        const optVal = opt.value.toLowerCase().trim();
                        if (optVal === codeLower || optText === codeLower || optText.startsWith(codeLower + ' ') || optText.startsWith('🧩 [' + codeLower) || optText.startsWith('📦 [' + codeLower)) {
                            foundVal = opt.value;
                            break;
                        }
                    }
                    if (foundVal) {
                        select.value = foundVal;
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        if (select.tomselect) {
                            select.tomselect.setValue(foundVal);
                        }
                    }
                });
            }
        }, 200);
    });
