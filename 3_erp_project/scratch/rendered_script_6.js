
    function openPaymentDrawer(e) {
        if (e && e.preventDefault) e.preventDefault();
        const backdrop = document.getElementById('drawerBackdrop');
        const drawer = document.getElementById('paymentDrawer');
        if (backdrop) {
            backdrop.style.setProperty('display', 'block', 'important');
            backdrop.style.setProperty('z-index', '100004', 'important');
            backdrop.classList.add('active');
        }
        if (drawer) {
            drawer.style.setProperty('display', 'block', 'important');
            drawer.style.setProperty('right', '0px', 'important');
            drawer.style.setProperty('z-index', '100005', 'important');
            drawer.classList.add('active');
        }
        try {
            if (typeof updateRecipientLoanDeductionSection === 'function') {
                updateRecipientLoanDeductionSection();
            }
        } catch(err) {
            console.error('Error updating loan section:', err);
        }
        return false;
    }
    window.openPaymentDrawer = openPaymentDrawer;

    function closePaymentDrawer() {
        closeAllDrawers();
    }
    window.closePaymentDrawer = closePaymentDrawer;

    const recipientLoanMap = {
        
        
        "jw_22": 0,
        
    };

    function updateRecipientLoanDeductionSection() {
        const select = document.querySelector('#paymentDrawer select[name="target_id"]');
        const targetId = select ? select.value : '';
        const container = document.getElementById('q-loan-deduct-container');
        const badge = document.getElementById('q-loan-avail-badge');
        const check = document.getElementById('q-enable-loan-deduct');
        const loanCutInput = document.getElementById('q-loan-cut-input');
        
        const loanBal = recipientLoanMap[targetId] || 0;
        if (loanBal > 0) {
            if (container) container.style.display = 'block';
            if (badge) badge.textContent = `Pending Loan: ₹${Math.round(loanBal).toLocaleString()}`;
            if (loanCutInput) loanCutInput.max = loanBal;
        } else {
            if (container) container.style.display = 'none';
            if (check) check.checked = false;
            onToggleLoanDeduction();
        }
        recalculateSplitPayout();
    }
    window.updateRecipientLoanDeductionSection = updateRecipientLoanDeductionSection;

    function onToggleLoanDeduction() {
        const check = document.getElementById('q-enable-loan-deduct');
        const body = document.getElementById('q-loan-deduct-body');
        const loanCutInput = document.getElementById('q-loan-cut-input');
        const isChecked = check ? check.checked : false;
        
        if (body) body.style.display = isChecked ? 'grid' : 'none';
        if (isChecked && loanCutInput && (!loanCutInput.value || parseFloat(loanCutInput.value) <= 0)) {
            const totalAmtInput = document.querySelector('#paymentDrawer input[name="amount"]');
            const totalAmt = parseFloat(totalAmtInput ? totalAmtInput.value : '0') || 0;
            const targetId = document.querySelector('#paymentDrawer select[name="target_id"]')?.value || '';
            const loanBal = recipientLoanMap[targetId] || 0;
            
            let recCut = 1000;
            if (loanBal < 1000) recCut = loanBal;
            if (totalAmt > 0 && recCut >= totalAmt) recCut = Math.max(0, totalAmt - 100);
            loanCutInput.value = recCut > 0 ? recCut : '';
        }
        recalculateSplitPayout();
    }
    window.onToggleLoanDeduction = onToggleLoanDeduction;

    function recalculateSplitPayout() {
        const totalAmtInput = document.querySelector('#paymentDrawer input[name="amount"]');
        const totalAmt = parseFloat(totalAmtInput ? totalAmtInput.value : '0') || 0;
        const check = document.getElementById('q-enable-loan-deduct');
        const loanCutInput = document.getElementById('q-loan-cut-input');
        const netDisplay = document.getElementById('q-net-cash-display');
        
        const isChecked = check ? check.checked : false;
        let loanCut = 0;
        if (isChecked && loanCutInput) {
            loanCut = parseFloat(loanCutInput.value || '0') || 0;
        }
        
        let netCash = totalAmt - loanCut;
        if (netCash < 0) netCash = 0;
        
        if (netDisplay) {
            netDisplay.textContent = `₹${netCash.toFixed(2)}`;
        }
    }
    window.recalculateSplitPayout = recalculateSplitPayout;

    function changeLedgerMonth(val) {
        if (!val) return;
        var monthStr = (typeof val === 'string' && val.length >= 7) ? val.substring(0, 7) : val;
        var currentTab = 'staff';
        try {
            var params = new URLSearchParams(window.location.search);
            currentTab = params.get('tab') || sessionStorage.getItem('ledger_active_tab') || 'staff';
        } catch (e) {}
        window.location.href = '/ledger/?tab=' + currentTab + '&month=' + monthStr;
    }
    window.changeLedgerMonth = changeLedgerMonth;

    window.ledgerNeedsRefresh = false;

    function closeAllDrawers() {
        const backdrop = document.getElementById('drawerBackdrop');
        if (backdrop) {
            backdrop.style.setProperty('display', 'none', 'important');
            backdrop.classList.remove('active');
        }
        document.querySelectorAll('.drawer').forEach(d => {
            d.style.setProperty('right', '-100vw', 'important');
            d.style.setProperty('display', 'none', 'important');
            d.classList.remove('active');
        });
        if (typeof currentProfileWorkerId !== 'undefined') currentProfileWorkerId = null;

        if (window.ledgerNeedsRefresh) {
            window.ledgerNeedsRefresh = false;
            let currentTab = 'staff';
            try {
                const params = new URLSearchParams(window.location.search);
                currentTab = params.get('tab') || sessionStorage.getItem('ledger_active_tab') || 'staff';
            } catch(e) {}
            sessionStorage.setItem('ledger_active_tab', currentTab);
            sessionStorage.setItem('ledger_scroll_pos', window.scrollY);
            location.reload();
        }
    }
    window.closeAllDrawers = closeAllDrawers;

    function renderAttendanceCalendar(data) {
        const grid = document.getElementById('attendance-calendar-grid');
        if (!grid) return;
        grid.innerHTML = '';
        
        let year = parseInt(data.year || data.year_num);
        let month = parseInt(data.month || data.month_num);
        
        if (isNaN(year) || isNaN(month)) {
            if (data.month_val && typeof data.month_val === 'string' && data.month_val.includes('-')) {
                const parts = data.month_val.split('-');
                year = parseInt(parts[0]);
                month = parseInt(parts[1]);
            } else if (data.month_str && typeof data.month_str === 'string' && data.month_str.includes('-')) {
                const parts = data.month_str.split('-');
                year = parseInt(parts[0]);
                month = parseInt(parts[1]);
            } else {
                const now = new Date();
                year = now.getFullYear();
                month = now.getMonth() + 1;
            }
        }

        const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        const nameEl = document.getElementById('calendar-month-name');
        if (nameEl) {
            if (data.month_name && data.month_name !== 'all' && data.month_name !== 'last_payment' && !data.month_name.includes('undefined')) {
                nameEl.innerText = data.month_name;
            } else {
                nameEl.innerText = `${monthNames[month-1]} ${year}`;
            }
        }

        const weekdays = ["S", "M", "T", "W", "T", "F", "S"];
        weekdays.forEach(w => {
            grid.innerHTML += `<div style="font-weight:bold; color:var(--text-secondary); padding:4px 0; text-align:center; font-size:11px;">${w}</div>`;
        });

        const attMap = {};
        (data.attendance || []).forEach(a => {
            if (a.raw_date) attMap[a.raw_date] = a;
        });

        const totalDays = new Date(year, month, 0).getDate();
        const firstDayIndex = new Date(year, month - 1, 1).getDay();

        for (let i = 0; i < firstDayIndex; i++) {
            grid.innerHTML += `<div></div>`;
        }

        for (let d = 1; d <= totalDays; d++) {
            const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            const att = attMap[dateStr];
            let bg = 'rgba(255,255,255,0.03)';
            let symbol = d;
            let color = 'var(--text-secondary)';
            let border = '1px solid var(--border-soft)';

            if (att) {
                if (att.raw_status === 'PRESENT') {
                    bg = 'rgba(16, 185, 129, 0.15)';
                    color = '#34d399';
                    border = '1px solid rgba(16, 185, 129, 0.3)';
                    symbol = `${d} ✓`;
                } else if (att.raw_status === 'ABSENT') {
                    bg = 'rgba(239, 68, 68, 0.15)';
                    color = '#f87171';
                    border = '1px solid rgba(239, 68, 68, 0.3)';
                    symbol = `${d} ✕`;
                } else if (att.raw_status === 'HALF_DAY') {
                    bg = 'rgba(245, 158, 11, 0.15)';
                    color = '#fbbf24';
                    border = '1px solid rgba(245, 158, 11, 0.3)';
                    symbol = `${d} =`;
                } else if (att.raw_status === 'HOLIDAY') {
                    bg = 'rgba(59, 130, 246, 0.15)';
                    color = '#60a5fa';
                    border = '1px solid rgba(59, 130, 246, 0.3)';
                    symbol = `${d} ★`;
                }
            }

            grid.innerHTML += `
                <div style="background:${bg}; color:${color}; border:${border}; border-radius:8px; padding:6px 2px; font-weight:bold; font-size:11px; text-align:center; min-height:40px; display:flex; flex-direction:column; align-items:center; justify-content:center;">
                    <span>${symbol}</span>
                    ${att && att.ot ? `<span style="font-size:9px; color:#fbbf24; margin-top:2px;">+${att.ot}h</span>` : ''}
                </div>`;
        }
    }
    window.renderAttendanceCalendar = renderAttendanceCalendar;

    let currentInternalWorkerId = null;
    let drawerWorkerCurrentMode = 'monthly';
    let drawerWorkerCurrentMonth = '2026-09';
    let drawerWorkerCurrentCategory = 'all';
    let drawerWorkerMonthPicker = null;

    function onWorkerDrawerModeChange(mode) {
        drawerWorkerCurrentMode = mode;
        const pickerBox = document.getElementById('w-drawer-month-picker-box');
        if (pickerBox) {
            pickerBox.style.display = (mode === 'monthly') ? 'inline-block' : 'none';
        }
        loadWorkerProfileLedger();
    }
    window.onWorkerDrawerModeChange = onWorkerDrawerModeChange;

    function setWorkerDrawerCategoryFilter(cat) {
        drawerWorkerCurrentCategory = cat;
        ['all', 'work', 'payment'].forEach(c => {
            const btn = document.getElementById('chip-wcat-' + c);
            if (btn) {
                if (c === cat) {
                    btn.style.background = 'var(--accent-blue)';
                    btn.style.color = 'white';
                    btn.style.border = 'none';
                } else {
                    btn.style.background = 'rgba(255,255,255,0.05)';
                    btn.style.color = 'var(--text-secondary)';
                    btn.style.border = '1px solid var(--border-soft)';
                }
            }
        });
        loadWorkerProfileLedger();
    }
    window.setWorkerDrawerCategoryFilter = setWorkerDrawerCategoryFilter;

    function showWorkerTab(tab) {
        document.querySelectorAll('.w-tab-content').forEach(c => c.style.display = 'none');
        const contentEl = document.getElementById('w-content-' + tab);
        if (contentEl) contentEl.style.display = 'block';
        
        const stmtTab = document.getElementById('w-tab-statement');
        const attTab = document.getElementById('w-tab-attendance');
        if (stmtTab) {
            stmtTab.style.borderBottom = tab === 'statement' ? '2px solid var(--accent-blue)' : 'none';
            stmtTab.style.color = tab === 'statement' ? 'var(--accent-blue)' : 'var(--text-secondary)';
        }
        if (attTab) {
            attTab.style.borderBottom = tab === 'attendance' ? '2px solid var(--accent-blue)' : 'none';
            attTab.style.color = tab === 'attendance' ? 'var(--accent-blue)' : 'var(--text-secondary)';
        }
    }
    window.showWorkerTab = showWorkerTab;

    async function loadWorkerProfileLedger() {
        if (!currentInternalWorkerId) return;

        let monthQuery = drawerWorkerCurrentMonth;
        if (drawerWorkerCurrentMode === 'all') monthQuery = 'all';
        else if (drawerWorkerCurrentMode === 'last_payment') monthQuery = 'last_payment';

        try {
            const response = await fetch(`/api/worker/${currentInternalWorkerId}/profile/?month=${monthQuery}&filter_type=${drawerWorkerCurrentCategory}`);
            const data = await response.json();
            renderWorkerProfileData(data);
        } catch (err) {
            console.error("Error loading worker profile:", err);
        }
    }
    window.loadWorkerProfileLedger = loadWorkerProfileLedger;

    function renderWorkerProfileData(data) {
        if (!data) return;
        const setTxt = (elId, val) => {
            const el = document.getElementById(elId);
            if (el) el.innerText = (val !== undefined && val !== null) ? val : '---';
        };

        setTxt('worker-profile-name', data.name);
        setTxt('worker-profile-id-view', data.employee_id);
        setTxt('worker-profile-designation-view', data.designation);
        setTxt('worker-profile-model', data.salary_model);
        setTxt('worker-profile-rate', '₹' + (data.base_rate || 0));
        
        setTxt('worker-profile-joining-view', data.joining_date);
        setTxt('worker-profile-identity-view', data.identity_no);
        setTxt('worker-profile-blood-view', data.blood_group);
        setTxt('worker-profile-shift-view', (data.shift_hours || 8) + 'h');
        
        // Update Worker Avatar initial
        const avatarSpan = document.querySelector('#workerProfileDrawer .drawer-header div span');
        if (avatarSpan && data.name) {
            avatarSpan.innerText = data.name.charAt(0).toUpperCase();
        }

        // Monthly Report links
        const targetMonth = data.month_val || drawerWorkerCurrentMonth;
        const link = document.getElementById('worker-report-link');
        if (link) link.href = `/worker/${data.id}/report/?month=${targetMonth}`;
        const drawerReportBtn = document.getElementById('w-drawer-monthly-report-btn');
        if (drawerReportBtn) drawerReportBtn.href = `/worker/${data.id}/report/?month=${targetMonth}`;

        const stats = data.stats || {};
        setTxt('worker-stat-earned', '₹' + (stats.earned || 0));
        setTxt('worker-stat-paid', '₹' + (stats.paid || 0));
        setTxt('worker-stat-balance', '₹' + (stats.balance || 0));
        
        // Monthly Summary Stats in Attendance Tab
        setTxt('stat-days-present', stats.present || 0);
        setTxt('stat-days-half', stats.half || 0);
        setTxt('stat-days-absent', stats.absent || 0);

        // Render Statement History Table
        const lbody = document.getElementById('worker-ledger-body');
        if (lbody) {
            lbody.innerHTML = '';
            if (!data.ledger || data.ledger.length === 0) {
                lbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-secondary);">No transactions recorded for this period.</td></tr>';
            } else {
                data.ledger.forEach(entry => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = '1px solid var(--border-soft)';
                    
                    let earnedText = '-';
                    if (entry.earned > 0) {
                        earnedText = '₹' + entry.earned.toFixed(0);
                    } else if (entry.type === 'ATTENDANCE' && entry.raw_status === 'ABSENT') {
                        earnedText = '<span style="color:#ef4444; font-size:11px;">₹0</span>';
                    }

                    let paidText = '-';
                    if (entry.paid > 0) {
                        paidText = '₹' + entry.paid.toFixed(0);
                    }

                    let actionsTdHtml = '';
                    let checkboxTdHtml = '';
                    
                    if (entry.type === 'PAYMENT') {
                        const pType = entry.payment_type || 'ADVANCE';
                        const pMode = entry.payment_mode || 'CASH';
                        const pDate = entry.raw_date || entry.date;
                        actionsTdHtml = `
                            <td style="padding:6px 10px; text-align:right; white-space:nowrap;">
                                <button type="button" onclick="openEditPaymentModal(${entry.id}, '${pDate}', ${entry.paid}, '${pType}', '${pMode}')" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer; margin-right:4px;">✏️ EDIT</button>
                                <button type="button" onclick="deletePayment(${entry.id}, ${entry.paid})" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer;">🗑️ DELETE</button>
                            </td>
                        `;
                        checkboxTdHtml = `
                            <td style="padding:10px; text-align:center;">
                                <input type="checkbox" class="w-tx-select-checkbox" data-tx-id="${entry.id}" data-entry-type="PAYMENT" onchange="updateBulkDeleteWorkerTxButton()" style="width:16px; height:16px; accent-color:#ef4444; cursor:pointer;">
                            </td>
                        `;
                    } else if (entry.type === 'STOCK') {
                        actionsTdHtml = `
                            <td style="padding:6px 10px; text-align:right; white-space:nowrap;">
                                <button type="button" onclick="deleteStockTx(${entry.id}, ${JSON.stringify(entry.description || '')})" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer;">🗑️ DELETE</button>
                            </td>
                        `;
                        checkboxTdHtml = `
                            <td style="padding:10px; text-align:center;">
                                <input type="checkbox" class="w-tx-select-checkbox" data-tx-id="${entry.id}" data-entry-type="TX" onchange="updateBulkDeleteWorkerTxButton()" style="width:16px; height:16px; accent-color:#ef4444; cursor:pointer;">
                            </td>
                        `;
                    } else {
                        actionsTdHtml = `<td style="padding:10px; text-align:right; color:var(--text-secondary); font-size:11px;">-</td>`;
                        checkboxTdHtml = `<td style="padding:10px; text-align:center; color:var(--text-secondary);">-</td>`;
                    }
                    

                    tr.innerHTML = `
                        ${checkboxTdHtml}
                        <td style="padding:10px; font-size:11px; white-space:nowrap;">${entry.date}</td>
                        <td style="padding:10px; font-size:11px;">${entry.description}</td>
                        <td style="padding:10px; text-align:right; font-weight:bold; color:#10b981;">${earnedText}</td>
                        <td style="padding:10px; text-align:right; font-weight:bold; color:#ef4444;">${paidText}</td>
                        ${actionsTdHtml}
                    `;
                    lbody.appendChild(tr);
                });
            }
        }

        // Render Attendance Calendar in Tab 2
        renderAttendanceCalendar(data);
    }
    window.renderWorkerProfileData = renderWorkerProfileData;

    function toggleSelectAllWorkerTx(masterCheckbox) {
        const isChecked = masterCheckbox.checked;
        document.querySelectorAll('.w-tx-select-checkbox').forEach(cb => {
            cb.checked = isChecked;
        });
        updateBulkDeleteWorkerTxButton();
    }
    window.toggleSelectAllWorkerTx = toggleSelectAllWorkerTx;

    function updateBulkDeleteWorkerTxButton() {
        const selected = document.querySelectorAll('.w-tx-select-checkbox:checked');
        const bulkBtn = document.getElementById('btn-w-bulk-delete-tx');
        const countSpan = document.getElementById('selectedWorkerTxCount');
        const masterCheck = document.getElementById('selectAllWorkerTxCheckbox');
        
        if (countSpan) countSpan.textContent = selected.length;
        if (bulkBtn) {
            bulkBtn.style.display = selected.length > 0 ? 'inline-flex' : 'none';
        }
        
        const allVisible = document.querySelectorAll('.w-tx-select-checkbox');
        if (masterCheck && allVisible.length > 0) {
            masterCheck.checked = (selected.length === allVisible.length);
        }
    }
    window.updateBulkDeleteWorkerTxButton = updateBulkDeleteWorkerTxButton;

    async function bulkDeleteSelectedWorkerTx() {
        const selected = document.querySelectorAll('.w-tx-select-checkbox:checked');
        if (selected.length === 0) return;

        const items = Array.from(selected).map(cb => ({
            id: parseInt(cb.getAttribute('data-tx-id')),
            type: cb.getAttribute('data-entry-type') || 'PAYMENT'
        }));

        if (!confirm(`Are you sure you want to delete ${items.length} selected transaction(s)?`)) {
            return;
        }

        try {
            const response = await fetch('/api/stock-transaction/bulk-delete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'
                },
                body: JSON.stringify({ items: items })
            });
            const data = await response.json();
            if (data.status === 'success') {
                window.ledgerNeedsRefresh = true;
                if (currentInternalWorkerId) {
                    loadWorkerProfileLedger();
                } else {
                    location.reload();
                }
            } else {
                alert('Error deleting entries: ' + (data.error || 'Failed to delete selected entries'));
            }
        } catch (err) {
            alert('Network error deleting entries: ' + err.message);
        }
    }
    window.bulkDeleteSelectedWorkerTx = bulkDeleteSelectedWorkerTx;

    function openWorkerProfile(id) {
        closeAllDrawers();
        currentInternalWorkerId = id;
        const params = new URLSearchParams(window.location.search);
        drawerWorkerCurrentMonth = params.get('month') || '2026-09';
        drawerWorkerCurrentCategory = 'all';

        const drawer = document.getElementById('workerProfileDrawer');
        const backdrop = document.getElementById('drawerBackdrop');
        if (drawer) {
            drawer.style.setProperty('display', 'block', 'important');
            drawer.style.setProperty('right', '0px', 'important');
            drawer.style.setProperty('z-index', '100005', 'important');
            drawer.classList.add('active');
        }
        if (backdrop) {
            backdrop.style.setProperty('display', 'block', 'important');
            backdrop.style.setProperty('z-index', '100004', 'important');
            backdrop.classList.add('active');
        }

        try {
            const modeSelect = document.getElementById('w-drawer-mode-selector');
            if (modeSelect) modeSelect.value = 'monthly';
            const pickerBox = document.getElementById('w-drawer-month-picker-box');
            if (pickerBox) pickerBox.style.display = 'inline-block';
            if (drawerWorkerMonthPicker && typeof drawerWorkerMonthPicker.setDate === 'function') {
                drawerWorkerMonthPicker.setDate('2026-09', false);
            }
            
            ['all', 'work', 'payment'].forEach(c => {
                const btn = document.getElementById('chip-wcat-' + c);
                if (btn) {
                    if (c === 'all') {
                        btn.style.background = 'var(--accent-blue)';
                        btn.style.color = 'white';
                        btn.style.border = 'none';
                    } else {
                        btn.style.background = 'rgba(255,255,255,0.05)';
                        btn.style.color = 'var(--text-secondary)';
                        btn.style.border = '1px solid var(--border-soft)';
                    }
                }
            });

            showWorkerTab('statement');
        } catch (err) {
            console.error('Error preparing worker drawer UI:', err);
        }

        loadWorkerProfileLedger();
    }
    window.openWorkerProfile = openWorkerProfile;

    let currentProfileWorkerId = null;
    let drawerCurrentMode = 'monthly';
    let drawerCurrentMonth = '2026-09';
    let drawerCurrentCategory = 'all';
    let drawerMonthPicker = null;

    function onDrawerModeChange(mode) {
        drawerCurrentMode = mode;
        const pickerBox = document.getElementById('drawer-month-picker-box');
        if (pickerBox) {
            pickerBox.style.display = (mode === 'monthly') ? 'inline-block' : 'none';
        }
        loadJobWorkerProfileLedger();
    }
    window.onDrawerModeChange = onDrawerModeChange;

    function setDrawerCategoryFilter(cat) {
        drawerCurrentCategory = cat;
        ['all', 'stock', 'payment'].forEach(c => {
            const btn = document.getElementById('chip-cat-' + c);
            if (btn) {
                if (c === cat) {
                    btn.style.background = 'var(--accent-blue)';
                    btn.style.color = 'white';
                    btn.style.border = 'none';
                } else {
                    btn.style.background = 'rgba(255,255,255,0.05)';
                    btn.style.color = 'var(--text-secondary)';
                    btn.style.border = '1px solid var(--border-soft)';
                }
            }
        });
        loadJobWorkerProfileLedger();
    }
    window.setDrawerCategoryFilter = setDrawerCategoryFilter;

    function showProfileTab(tab) {
        document.querySelectorAll('.profile-tab').forEach(t => t.style.display = 'none');
        const targetContent = document.getElementById('profile-tab-' + tab);
        if (targetContent) targetContent.style.display = 'block';
        
        const btnHistory = document.getElementById('tab-btn-history');
        const btnRates = document.getElementById('tab-btn-rates');
        if (btnHistory) {
            btnHistory.style.color = 'var(--text-secondary)';
            btnHistory.style.borderBottom = 'none';
        }
        if (btnRates) {
            btnRates.style.color = 'var(--text-secondary)';
            btnRates.style.borderBottom = 'none';
        }
        
        const btn = document.getElementById('tab-btn-' + tab);
        if (btn) {
            btn.style.color = 'var(--accent-blue)';
            btn.style.borderBottom = '2px solid var(--accent-blue)';
        }
    }
    window.showProfileTab = showProfileTab;

    function closeJobWorkerProfile() {
        closeAllDrawers();
    }
    window.closeJobWorkerProfile = closeJobWorkerProfile;

    function renderJobWorkerProfileData(data) {
        if (!data) return;
        const nameEl = document.getElementById('profile-worker-name');
        if (nameEl) nameEl.innerText = data.name || 'Job Worker Profile';

        // Dynamic Metadata Card Population
        const metaGrid = document.getElementById('profile-meta-grid');
        if (metaGrid) {
            if (data.process === 'casting') {
                metaGrid.style.gridTemplateColumns = 'repeat(3, 1fr)';
                metaGrid.innerHTML = `
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Total Weight</label>
                        <span style="font-weight:bold; font-size:14px; color:white;">${(data.total_casting_wt || 0).toFixed(1)} kg</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Payable</label>
                        <span style="font-weight:bold; font-size:14px; color:#10b981;">₹${(data.total_earned || 0).toFixed(0)}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Advance Paid</label>
                        <span style="font-weight:bold; font-size:14px; color:#ef4444;">₹${(data.total_paid || 0).toFixed(0)}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Net Payable</label>
                        <span style="font-weight:bold; font-size:14px; color:var(--accent-blue);">₹${(data.balance || 0).toFixed(0)}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Loan Balance</label>
                        <span style="font-weight:bold; font-size:14px; color:#f59e0b;">₹${(data.loan_balance || 0).toFixed(0)}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Service Process</label>
                        <span style="font-weight:bold; font-size:14px; color:var(--text-secondary); text-transform:capitalize;">Casting</span>
                    </div>
                `;
            } else {
                metaGrid.style.gridTemplateColumns = '1fr 1fr';
                metaGrid.innerHTML = `
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Service Process</label>
                        <span style="font-weight:bold; font-size:14px; color:var(--accent-blue); text-transform:capitalize;">${data.process || '---'}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">GST Number</label>
                        <span style="font-weight:bold; font-size:14px; color:white;">${data.gst || 'N/A'}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Phone / Contact</label>
                        <span style="font-weight:bold; font-size:14px; color:white;">${data.phone || '---'}</span>
                    </div>
                    <div>
                        <label style="font-size:10px; color:var(--text-secondary); text-transform:uppercase; display:block; margin-bottom:4px;">Email</label>
                        <span style="font-weight:bold; font-size:14px; color:white;">${data.email || '---'}</span>
                    </div>
                `;
            }
        }

        // Assignments
        const tbody = document.getElementById('profile-assignments-body');
        if (tbody) {
            tbody.innerHTML = '';
            if (!data.items || data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; padding:20px; color:var(--text-secondary);">No item rates linked yet.</td></tr>';
            } else {
                data.items.forEach(item => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = '1px solid var(--border-soft)';
                    
                    let rateColHtml = '';
                    let actionColHtml = '';
                    
                    rateColHtml = `
                        <td style="padding:6px 10px; text-align:right;">
                            <div style="display:inline-flex; align-items:center; justify-content:flex-end; gap:6px;">
                                <span style="color:var(--text-secondary); font-size:12px; font-weight:bold;">₹</span>
                                <input type="number" step="0.01" min="0" value="${parseFloat(item.rate || 0).toFixed(2)}" 
                                       id="alloc-rate-input-${item.id}"
                                       data-orig-rate="${parseFloat(item.rate || 0).toFixed(2)}"
                                       onchange="saveAllocationRate('${item.id}', this)"
                                       onkeydown="if(event.key==='Enter'){event.preventDefault(); this.blur();}"
                                       style="width:90px; padding:5px 8px; background:var(--input-dark, #0f172a); border:1px solid var(--border-soft); border-radius:6px; color:#10b981; font-weight:bold; font-size:13px; text-align:right; transition:all 0.2s;">
                                <button type="button" onclick="saveAllocationRate('${item.id}', document.getElementById('alloc-rate-input-${item.id}'))" 
                                        id="alloc-save-btn-${item.id}" 
                                        style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); border-radius:6px; padding:4px 8px; font-size:11px; font-weight:700; cursor:pointer;" title="Save Rate">💾 Save</button>
                            </div>
                        </td>
                    `;
                    actionColHtml = `
                        <td style="padding:6px 10px; text-align:right;">
                            <button type="button" onclick="removeAllocation('${item.id}')" style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.25); color:#ef4444; border-radius:6px; padding:4px 8px; cursor:pointer; font-size:11px; font-weight:bold;" title="Remove this item rate">✕</button>
                        </td>
                    `;
                    

                    tr.innerHTML = `
                        <td style="padding:10px; font-size:13px; font-weight:600; color:white;">
                            ${item.item_name}
                            ${item.item_code && item.item_code !== item.item_name ? `<span style="color:var(--text-secondary); font-size:11px; margin-left:5px;">(${item.item_code})</span>` : ''}
                        </td>
                        ${rateColHtml}
                        ${actionColHtml}
                    `;
                    tbody.appendChild(tr);
                });
            }
        }

        // Ledger
        const lbody = document.getElementById('profile-ledger-body');
        if (lbody) {
            lbody.innerHTML = '';

            if (!data.ledger || data.ledger.length === 0) {
                lbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-secondary);">No transactions recorded for this period.</td></tr>';
            } else {
                data.ledger.forEach(entry => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = '1px solid var(--border-soft)';
                    
                    let earnedText = '-';
                    if (entry.is_inward) {
                        if (entry.is_raw_material) {
                            earnedText = '-';
                        } else if (entry.has_rate) {
                            earnedText = '₹' + entry.earned.toFixed(0);
                        } else {
                            earnedText = '<span style="color:#ef4444; font-size:10px; font-weight:800; background:rgba(239,68,68,0.1); padding:2px 6px; border-radius:4px; display:inline-block;">₹0 (No Rate Set)</span>';
                        }
                    } else if (entry.earned > 0) {
                        earnedText = '₹' + entry.earned.toFixed(0);
                    }

                    let actionsTdHtml = '';
                    
                    if (entry.type === 'PAYMENT') {
                        const pType = entry.payment_type || 'ADVANCE';
                        const pMode = entry.payment_mode || 'CASH';
                        actionsTdHtml = `
                            <td style="padding:6px 10px; text-align:right; white-space:nowrap;">
                                <button type="button" onclick="openEditPaymentModal(${entry.id}, '${entry.date}', ${entry.paid}, '${pType}', '${pMode}')" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer; margin-right:4px;">✏️ EDIT</button>
                                <button type="button" onclick="deletePayment(${entry.id}, ${entry.paid})" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer;">🗑️ DELETE</button>
                            </td>
                        `;
                    } else {
                        actionsTdHtml = `
                            <td style="padding:6px 10px; text-align:right; white-space:nowrap;">
                                <button type="button" onclick="deleteStockTx(${entry.id}, ${JSON.stringify(entry.description || '')})" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer;">🗑️ DELETE</button>
                            </td>
                        `;
                    }
                    

                    let checkboxTdHtml = '';
                    
                    checkboxTdHtml = `
                        <td style="padding:10px; text-align:center;">
                            <input type="checkbox" class="tx-select-checkbox" data-tx-id="${entry.id}" data-entry-type="${entry.type === 'PAYMENT' ? 'PAYMENT' : 'TX'}" onchange="updateBulkDeleteTxButton()" style="width:16px; height:16px; accent-color:#ef4444; cursor:pointer;">
                        </td>
                    `;
                    

                    tr.innerHTML = `
                        ${checkboxTdHtml}
                        <td style="padding:10px; font-size:11px;">${entry.date}</td>
                        <td style="padding:10px; font-size:11px;">${entry.description}</td>
                        <td style="padding:10px; text-align:right; font-weight:bold; color:#10b981;">${earnedText}</td>
                        <td style="padding:10px; text-align:right; font-weight:bold; color:#ef4444;">${entry.paid > 0 ? '₹'+entry.paid.toFixed(0) : '-'}</td>
                        ${actionsTdHtml}
                    `;
                    lbody.appendChild(tr);
                });
            }
        }

        const calContainer = document.getElementById('profile-history-calendar-container');
        const ledgerTable = document.getElementById('profile-ledger-table');
        const titleH3 = document.getElementById('profile-history-title');

        if (data.process === 'casting' && data.calendar_weeks) {
            if (ledgerTable) ledgerTable.style.display = 'none';
            if (calContainer) {
                calContainer.style.display = 'block';
                let html = `
                    <style>
                        .drawer-calendar-grid {
                            display: grid;
                            grid-template-columns: repeat(7, 1fr);
                            gap: 4px;
                            background: rgba(255, 255, 255, 0.01);
                            border: 1px solid var(--border-soft);
                            padding: 8px;
                            border-radius: 8px;
                            margin-top: 10px;
                        }
                        .drawer-cal-header {
                            text-align: center;
                            font-weight: bold;
                            font-size: 10px;
                            text-transform: uppercase;
                            color: var(--text-secondary);
                            padding-bottom: 6px;
                            border-bottom: 1px solid var(--border-soft);
                        }
                        .drawer-cal-cell {
                            aspect-ratio: 1.1;
                            border: 1px solid var(--border-soft);
                            border-radius: 6px;
                            background: rgba(255, 255, 255, 0.01);
                            padding: 4px;
                            display: flex;
                            flex-direction: column;
                            justify-content: space-between;
                            position: relative;
                            min-height: 42px;
                        }
                        .drawer-cal-cell.active-work {
                            background: rgba(59, 130, 246, 0.08);
                            border-color: var(--accent-blue);
                        }
                        .drawer-cal-cell.active-payment {
                            background: rgba(239, 68, 68, 0.08);
                            border-color: #ef4444;
                        }
                        .drawer-cal-cell.active-work.active-payment {
                            background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(239, 68, 68, 0.08) 100%);
                            border-color: var(--accent-blue);
                        }
                        .drawer-cal-cell.holiday {
                            background: rgba(245, 158, 11, 0.06);
                            border-color: #f59e0b;
                        }
                        .drawer-cal-cell.holiday.active-work {
                            background: linear-gradient(135deg, rgba(245, 158, 11, 0.06) 0%, rgba(59, 130, 246, 0.08) 100%);
                            border-color: #f59e0b;
                        }
                        .drawer-day-num {
                            font-size: 10px;
                            font-weight: bold;
                            color: var(--text-secondary);
                        }
                        .drawer-day-wt {
                            font-size: 10px;
                            font-weight: 700;
                            color: white;
                            text-align: center;
                            margin: auto 0;
                        }
                        .drawer-day-pmt {
                            font-size: 9px;
                            font-weight: 800;
                            color: #ef4444;
                            text-align: center;
                            background: rgba(239, 68, 68, 0.1);
                            padding: 1px 2px;
                            border-radius: 3px;
                        }
                        .drawer-holiday-badge {
                            position: absolute;
                            top: 3px;
                            right: 3px;
                            color: #f59e0b;
                            font-size: 8px;
                            font-weight: bold;
                        }
                    </style>
                    <div class="drawer-calendar-grid">
                        <div class="drawer-cal-header">Sun</div>
                        <div class="drawer-cal-header">Mon</div>
                        <div class="drawer-cal-header">Tue</div>
                        <div class="drawer-cal-header">Wed</div>
                        <div class="drawer-cal-header">Thu</div>
                        <div class="drawer-cal-header">Fri</div>
                        <div class="drawer-cal-header">Sat</div>
                `;

                data.calendar_weeks.forEach(week => {
                    week.forEach(day => {
                        if (day) {
                            const isWork = day.casting_weight > 0;
                            const isPmt = day.advance_paid > 0;
                            const isHol = day.is_holiday;
                            
                            let cellClasses = ['drawer-cal-cell'];
                            if (isWork) cellClasses.push('active-work');
                            if (isPmt) cellClasses.push('active-payment');
                            if (isHol) cellClasses.push('holiday');

                            html += `
                                <div class="${cellClasses.join(' ')}">
                                    <div class="drawer-day-num">${day.day}</div>
                            `;

                            if (isHol) {
                                html += `<span class="drawer-holiday-badge" title="Holiday: ${day.holiday_name}">★</span>`;
                            }

                            if (isWork) {
                                html += `<div class="drawer-day-wt">${day.casting_weight.toFixed(1)} kg</div>`;
                            }

                            if (isPmt) {
                                html += `<div class="drawer-day-pmt">-₹${day.advance_paid.toFixed(0)}</div>`;
                            }

                            html += `</div>`;
                        } else {
                            html += `<div class="drawer-cal-cell" style="opacity: 0.15; border-style: dashed;"></div>`;
                        }
                    });
                });

                html += `</div>`;
                calContainer.innerHTML = html;
            }
            if (titleH3) titleH3.innerText = `CASTING WORK & EARNINGS - ${data.month_name}`;
        } else {
            if (calContainer) calContainer.style.display = 'none';
            if (ledgerTable) ledgerTable.style.display = 'table';
            if (titleH3) titleH3.innerText = "RECENT TRANSACTIONS";
        }
    }
    window.renderJobWorkerProfileData = renderJobWorkerProfileData;

    async function loadJobWorkerProfileLedger() {
        if (!currentProfileWorkerId) return;

        let monthQuery = drawerCurrentMonth;
        if (drawerCurrentMode === 'all') monthQuery = 'all';
        else if (drawerCurrentMode === 'last_payment') monthQuery = 'last_payment';

        try {
            const response = await fetch(`/api/job-worker/${currentProfileWorkerId}/profile/?month=${monthQuery}&filter_type=${drawerCurrentCategory}`);
            const data = await response.json();
            renderJobWorkerProfileData(data);
        } catch (err) {
            console.error("Error loading job worker profile:", err);
        }
    }
    window.loadJobWorkerProfileLedger = loadJobWorkerProfileLedger;

    async function openJobWorkerProfile(id) {
        closeAllDrawers();
        currentProfileWorkerId = id;
        const params = new URLSearchParams(window.location.search);
        drawerCurrentMonth = params.get('month') || '2026-09';
        drawerCurrentCategory = 'all';

        const drawer = document.getElementById('jobWorkerProfileDrawer');
        const backdrop = document.getElementById('drawerBackdrop');
        if (drawer) {
            drawer.style.setProperty('display', 'block', 'important');
            drawer.style.setProperty('right', '0px', 'important');
            drawer.style.setProperty('z-index', '100005', 'important');
            drawer.classList.add('active');
        }
        if (backdrop) {
            backdrop.style.setProperty('display', 'block', 'important');
            backdrop.style.setProperty('z-index', '100004', 'important');
            backdrop.classList.add('active');
        }

        try {
            const modeSelect = document.getElementById('drawer-mode-selector');
            if (modeSelect) modeSelect.value = 'monthly';
            const pickerBox = document.getElementById('drawer-month-picker-box');
            if (pickerBox) pickerBox.style.display = 'inline-block';
            if (drawerMonthPicker && typeof drawerMonthPicker.setDate === 'function') {
                drawerMonthPicker.setDate('2026-09', false);
            }
            
            ['all', 'stock', 'payment'].forEach(c => {
                const btn = document.getElementById('chip-cat-' + c);
                if (btn) {
                    if (c === 'all') {
                        btn.style.background = 'var(--accent-blue)';
                        btn.style.color = 'white';
                        btn.style.border = 'none';
                    } else {
                        btn.style.background = 'rgba(255,255,255,0.05)';
                        btn.style.color = 'var(--text-secondary)';
                        btn.style.border = '1px solid var(--border-soft)';
                    }
                }
            });

            if (typeof resetRateRowsContainer === 'function') resetRateRowsContainer();
            showProfileTab('history');
        } catch (err) {
            console.error('Error preparing profile drawer UI:', err);
        }

        loadJobWorkerProfileLedger();
    }
    window.openJobWorkerProfile = openJobWorkerProfile;

    async function saveAllocationRate(allocId, inputEl) {
        if (!inputEl) return;
        const newRate = parseFloat(inputEl.value);
        if (isNaN(newRate) || newRate < 0) {
            alert("⚠️ Please enter a valid non-negative rate.");
            inputEl.value = inputEl.dataset.origRate || "0.00";
            return;
        }

        const saveBtn = document.getElementById(`alloc-save-btn-${allocId}`);
        if (saveBtn) {
            saveBtn.innerText = "⏳";
            saveBtn.disabled = true;
        }
        inputEl.style.borderColor = "var(--accent-blue)";

        try {
            const formData = new FormData();
            formData.append('rate', newRate);
            const response = await fetch(`/api/allocation/${allocId}/update-rate/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'
                }
            });
            const data = await response.json();
            if (data.status === 'success') {
                inputEl.dataset.origRate = parseFloat(data.rate).toFixed(2);
                inputEl.value = parseFloat(data.rate).toFixed(2);
                inputEl.style.borderColor = "#10b981";
                if (saveBtn) {
                    saveBtn.innerText = "✅ Saved";
                    saveBtn.style.color = "#10b981";
                    saveBtn.style.borderColor = "#10b981";
                    setTimeout(() => {
                        saveBtn.innerText = "💾 Save";
                        saveBtn.style.color = "#60a5fa";
                        saveBtn.style.borderColor = "rgba(59,130,246,0.3)";
                        saveBtn.disabled = false;
                        inputEl.style.borderColor = "var(--border-soft)";
                    }, 1200);
                }
            } else {
                alert('Error: ' + (data.error || 'Failed to update rate'));
                inputEl.value = inputEl.dataset.origRate || "0.00";
                if (saveBtn) {
                    saveBtn.innerText = "💾 Save";
                    saveBtn.disabled = false;
                }
            }
        } catch (err) {
            alert('Error updating rate: ' + err.message);
            inputEl.value = inputEl.dataset.origRate || "0.00";
            if (saveBtn) {
                saveBtn.innerText = "💾 Save";
                saveBtn.disabled = false;
            }
        }
    }
    window.saveAllocationRate = saveAllocationRate;

    async function removeAllocation(id) {
        if (!confirm('Remove this item rate allocation?')) return;
        try {
            const res = await fetch(`/api/allocation/${id}/delete/`, {
                method: 'POST',
                headers: {'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'}
            });
            const data = await res.json();
            if (data.status === 'success') {
                if (typeof loadJobWorkerProfileLedger === 'function') {
                    loadJobWorkerProfileLedger();
                }
            } else {
                alert('Error: ' + (data.error || 'Failed to remove rate'));
            }
        } catch (e) {
            alert('Network error removing rate: ' + e.message);
        }
    }
    window.removeAllocation = removeAllocation;

    // MULTI-ROW ITEM RATE ALLOCATOR LOGIC
    let rateRowCounter = 0;
    const rateTomSelects = {};

    const itemOptionsHTML = `
        <option value="">Type & search item code or name...</option>
        
        <option value="192">C - Casting</option>
        
        <option value="70">D0 - Dasta 0 (OM)</option>
        
        <option value="71">D1 - Dasta 1 (OM)</option>
        
        <option value="72">D2 - Dasta 2 (OM)</option>
        
        <option value="73">D3 - Dasta 3 (OM)</option>
        
        <option value="74">D4 - Dasta 4 (OM)</option>
        
        <option value="75">D5 - Dasta 5 (OM)</option>
        
        <option value="76">D6 - Dasta 6 (OM)</option>
        
        <option value="77">D7 - Dasta 7 (OM)</option>
        
        <option value="90">DD - DDhakan (OM)</option>
        
        <option value="89">DH - Dhakan (OM)</option>
        
        <option value="193">GENERAL - General Casting Weight</option>
        
        <option value="132">HA - Handle</option>
        
        <option value="78">HD0 - HDasta 0 (OM)</option>
        
        <option value="79">HD1 - HDasta 1 (OM)</option>
        
        <option value="80">HD2 - HDasta 2 (OM)</option>
        
        <option value="81">HD3 - HDasta 3 (OM)</option>
        
        <option value="82">HD4 - HDasta 4 (OM)</option>
        
        <option value="83">HD5 - HDasta 5 (OM)</option>
        
        <option value="59">HK0 - HKhal 0 (OM)</option>
        
        <option value="140">HK0+HD0 - HKhal 0 + HDasta 0</option>
        
        <option value="60">HK1 - HKhal 1 (OM)</option>
        
        <option value="142">HK1+HD1 - HKhal 1 + HDasta 1</option>
        
        <option value="61">HK2 - HKhal 2 (OM)</option>
        
        <option value="144">HK2+HD2 - HKhal 2 + HDasta 2</option>
        
        <option value="62">HK3 - HKhal 3 (OM)</option>
        
        <option value="146">HK3+HD3 - HKhal 3 + HDasta 3</option>
        
        <option value="63">HK4 - HKhal 4 (OM)</option>
        
        <option value="148">HK4+HD4 - HKhal 4 + HDasta 4</option>
        
        <option value="64">HK5 - HKhal 5 (OM)</option>
        
        <option value="150">HK5+HD5 - HKhal 5 + HDasta 5</option>
        
        <option value="51">K0 - Khal 0 (OM)</option>
        
        <option value="152">K0+D0 - Khal 0 + Dasta 0</option>
        
        <option value="52">K1 - Khal 1 (OM)</option>
        
        <option value="154">K1+D1 - Khal 1 + Dasta 1</option>
        
        <option value="53">K2 - Khal 2 (OM)</option>
        
        <option value="156">K2+D2 - Khal 2 + Dasta 2</option>
        
        <option value="54">K3 - Khal 3 (OM)</option>
        
        <option value="158">K3+D3 - Khal 3 + Dasta 3</option>
        
        <option value="55">K4 - Khal 4 (OM)</option>
        
        <option value="160">K4+D4 - Khal 4 + Dasta 4</option>
        
        <option value="56">K5 - Khal 5 (OM)</option>
        
        <option value="162">K5+D5 - Khal 5 + Dasta 5</option>
        
        <option value="57">K6 - Khal 6 (OM)</option>
        
        <option value="164">K6+D6 - Khal 6 + Dasta 6</option>
        
        <option value="58">K7 - Khal 7 (OM)</option>
        
        <option value="166">K7+D7 - Khal 7 + Dasta 7</option>
        
        <option value="190">KP - Kitchen Press</option>
        
        <option value="191">LM - Lemon Squzeer</option>
        
        <option value="167">P7 - Pipe 7</option>
        
        <option value="168">P8 - Pipe 8</option>
        
        <option value="169">P9 - Pipe 9</option>
        
        <option value="84">PD1 - PDasta1 (OM)</option>
        
        <option value="85">PD2 - PDasta2 (OM)</option>
        
        <option value="86">PD3 - PDasta3 (OM)</option>
        
        <option value="87">PD4 - PDasta4 (OM)</option>
        
        <option value="88">PD5 - PDasta5 (OM)</option>
        
        <option value="194">PIPE 1.2</option>
        
        <option value="65">PK1 - PKhal 1 (OM)</option>
        
        <option value="176">PK1+PD1 - PKhal 1 + PDasta1</option>
        
        <option value="66">PK2 - PKhal 2 (OM)</option>
        
        <option value="178">PK2+PD2 - PKhal 2 + PDasta2</option>
        
        <option value="67">PK3 - PKhal 3 (OM)</option>
        
        <option value="180">PK3+PD3 - PKhal 3 + PDasta3</option>
        
        <option value="68">PK4 - PKhal 4 (OM)</option>
        
        <option value="69">PK5 - PKhal 5 (OM)</option>
        
        <option value="183">PK5+PD5 - PKhal 5 + PDasta5</option>
        
        <option value="226">Ring</option>
        
        <option value="184">S7 - Sancha 7</option>
        
        <option value="185">S8 - Sancha 8</option>
        
        <option value="186">S9 - Sancha 9</option>
        
        <option value="187">SC7 - Screw 7</option>
        
        <option value="188">SC8 - Screw 8</option>
        
        <option value="189">SC9 - Screw 9</option>
        
        <option value="196">SCB2 - SS Chopping Board MEDIUM</option>
        
        <option value="197">SCB3 - SS Chopping Board LARGE</option>
        
        <option value="198">SCT2 - SS CT Chopping Board Medium</option>
        
        <option value="199">SCT3 - SS CT Chopping Board Large</option>
        
        <option value="195">rod10.8 - ss rod</option>
        
    `;

    function resetRateRowsContainer() {
        Object.keys(rateTomSelects).forEach(rowId => {
            if (rateTomSelects[rowId] && typeof rateTomSelects[rowId].destroy === 'function') {
                try { rateTomSelects[rowId].destroy(); } catch(e){}
                delete rateTomSelects[rowId];
            }
        });
        const container = document.getElementById('rate-rows-container');
        if (container) container.innerHTML = '';
        rateRowCounter = 0;
        addRateRow();
    }
    window.resetRateRowsContainer = resetRateRowsContainer;

    function addRateRow(defaultItemId = '', defaultRate = '') {
        rateRowCounter++;
        const rowId = rateRowCounter;
        const container = document.getElementById('rate-rows-container');
        if (!container) return;

        const div = document.createElement('div');
        div.id = `rate-row-${rowId}`;
        div.style.cssText = 'display:flex; gap:10px; align-items:center;';

        div.innerHTML = `
            <div style="flex:1;">
                <select id="rate-item-select-${rowId}">
                    ${itemOptionsHTML}
                </select>
            </div>
            <input type="number" id="rate-input-${rowId}" value="${defaultRate}" step="0.01" min="0" placeholder="Rate ₹" style="width:110px; background:#1e293b; color:white; border:1px solid var(--border-soft); padding:8px 10px; border-radius:8px; font-weight:bold; font-size:13px;">
            <button type="button" onclick="removeRateRow(${rowId})" style="background:rgba(239, 68, 68, 0.15); color:#f87171; border:1px solid rgba(239, 68, 68, 0.3); padding:8px 12px; border-radius:8px; cursor:pointer; font-weight:bold; font-size:12px;" title="Remove row">✕</button>
        `;

        container.appendChild(div);

        const selectEl = document.getElementById(`rate-item-select-${rowId}`);
        if (selectEl && typeof TomSelect !== 'undefined') {
            try {
                rateTomSelects[rowId] = new TomSelect(selectEl, {
                    create: false,
                    placeholder: 'Type & search item code or name...',
                    maxOptions: 1000,
                    sortField: { field: 'text', direction: 'asc' }
                });
                if (defaultItemId) {
                    rateTomSelects[rowId].setValue(defaultItemId);
                }
            } catch(e) {
                console.error("TomSelect init error on rate row:", e);
            }
        }
    }
    window.addRateRow = addRateRow;

    function removeRateRow(rowId) {
        if (rateTomSelects[rowId]) {
            try { rateTomSelects[rowId].destroy(); } catch(e){}
            delete rateTomSelects[rowId];
        }
        const el = document.getElementById(`rate-row-${rowId}`);
        if (el) el.remove();
        
        const container = document.getElementById('rate-rows-container');
        if (container && container.children.length === 0) {
            addRateRow();
        }
    }
    window.removeRateRow = removeRateRow;

    async function saveAllWorkerRates() {
        const allocations = [];
        
        Object.keys(rateTomSelects).forEach(rowId => {
            const ts = rateTomSelects[rowId];
            const itemId = ts ? ts.getValue() : (document.getElementById(`rate-item-select-${rowId}`)?.value || '');
            const rateInput = document.getElementById(`rate-input-${rowId}`);
            const rate = rateInput ? rateInput.value : '';

            if (itemId && rate !== '' && rate !== null && !isNaN(rate) && parseFloat(rate) >= 0) {
                allocations.push({ item_id: itemId, rate: rate });
            }
        });

        if (allocations.length === 0) {
            const container = document.getElementById('rate-rows-container');
            if (container) {
                container.querySelectorAll('[id^="rate-row-"]').forEach(row => {
                    const sel = row.querySelector('select');
                    const inp = row.querySelector('input[type="number"]');
                    if (sel && inp && sel.value && inp.value && !isNaN(inp.value) && parseFloat(inp.value) >= 0) {
                        allocations.push({ item_id: sel.value, rate: inp.value });
                    }
                });
            }
        }

        if (allocations.length === 0) {
            return alert('⚠️ Please search/select an item and enter a valid rate for at least one row!');
        }

        const fd = new FormData();
        fd.append('worker_id', 'jw_' + currentProfileWorkerId);
        fd.append('allocations', JSON.stringify(allocations));

        try {
            const res = await fetch('/api/allocation/add/', {
                method: 'POST',
                body: fd,
                headers: {'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'}
            });
            const data = await res.json();
            if (data.status === 'success') {
                resetRateRowsContainer();
                if (typeof loadJobWorkerProfileLedger === 'function') {
                    loadJobWorkerProfileLedger();
                }
            } else {
                alert('⚠️ ' + (data.error || 'Failed to save item rates'));
            }
        } catch (err) {
            console.error(err);
            alert('⚠️ Network error saving item rates');
        }
    }
    window.saveAllWorkerRates = saveAllWorkerRates;

    let currentDuesData = {
        targetId: null,
        targetName: '',
        monthlyDue: 0,
        runningDue: 0,
        isJobWorker: false,
        selectedScope: 'MONTHLY',
        selectedMonth: '2026-09'
    };

    function populateSettlementMonths(selectedMonth) {
        const sel = document.getElementById('scope-target-month');
        if (!sel) return;
        sel.innerHTML = '';
        
        const today = new Date();
        const curYear = today.getFullYear();
        const curMonth = today.getMonth();
        const monthsNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        
        for (let i = 0; i < 6; i++) {
            let d = new Date(curYear, curMonth - i, 1);
            let yyyy = d.getFullYear();
            let mm = String(d.getMonth() + 1).padStart(2, '0');
            let mVal = `${yyyy}-${mm}`;
            let mLabel = `${monthsNames[d.getMonth()]} ${yyyy}`;
            if (i === 0) mLabel += " (Current)";
            else if (i === 1) mLabel += " (Last Month)";
            
            let opt = document.createElement('option');
            opt.value = mVal;
            opt.textContent = mLabel;
            if (mVal === selectedMonth) opt.selected = true;
            sel.appendChild(opt);
        }
    }
    window.populateSettlementMonths = populateSettlementMonths;

    function selectSettlementScope(scope) {
        currentDuesData.selectedScope = scope;
        const monthlyCard = document.getElementById('scope-card-monthly');
        const todayCard = document.getElementById('scope-card-today');
        const monthlyRadio = document.getElementById('scope-radio-monthly');
        const todayRadio = document.getElementById('scope-radio-today');
        const amountInput = document.querySelector('#paymentDrawer input[name="amount"]');
        const notesInput = document.getElementById('q-payment-notes');

        if (scope === 'MONTHLY') {
            if (monthlyRadio) monthlyRadio.checked = true;
            if (monthlyCard) {
                monthlyCard.style.background = 'rgba(99, 102, 241, 0.15)';
                monthlyCard.style.border = '2px solid #6366f1';
                if (monthlyCard.querySelector('div')) monthlyCard.querySelector('div').style.color = '#818cf8';
            }
            if (todayCard) {
                todayCard.style.background = 'rgba(255, 255, 255, 0.03)';
                todayCard.style.border = '1px solid rgba(255, 255, 255, 0.12)';
                if (todayCard.querySelector('div')) todayCard.querySelector('div').style.color = '#94a3b8';
            }
            
            if (amountInput) {
                amountInput.value = currentDuesData.monthlyDue > 0 ? Math.round(currentDuesData.monthlyDue) : '';
            }
            if (notesInput) {
                const sel = document.getElementById('scope-target-month');
                const selText = (sel && sel.selectedIndex >= 0 && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text.split('(')[0].trim() : (currentDuesData.selectedMonth || '');
                const settlementLabel = currentDuesData.isJobWorker ? 'Job Work Settlement' : 'Salary Settlement';
                notesInput.value = `${selText} ${settlementLabel}`;
            }
        } else if (scope === 'TILL_TODAY') {
            if (todayRadio) todayRadio.checked = true;
            if (todayCard) {
                todayCard.style.background = 'rgba(16, 185, 129, 0.15)';
                todayCard.style.border = '2px solid #10b981';
                if (todayCard.querySelector('div')) todayCard.querySelector('div').style.color = '#34d399';
            }
            if (monthlyCard) {
                monthlyCard.style.background = 'rgba(255, 255, 255, 0.03)';
                monthlyCard.style.border = '1px solid rgba(255, 255, 255, 0.12)';
                if (monthlyCard.querySelector('div')) monthlyCard.querySelector('div').style.color = '#94a3b8';
            }
            
            if (amountInput) {
                amountInput.value = currentDuesData.runningDue > 0 ? Math.round(currentDuesData.runningDue) : '';
            }
            if (notesInput) {
                const settlementLabel = currentDuesData.isJobWorker ? 'Job Work Settlement' : 'Salary Settlement';
                notesInput.value = `${currentDuesData.targetName} Running ${settlementLabel} (Till Today)`;
            }
        }
        if (typeof recalculateSplitPayout === 'function') recalculateSplitPayout();
    }
    window.selectSettlementScope = selectSettlementScope;

    function openQuickSettlementModal(targetId, targetName, amount, isJobWorker, periodName) {
        if (typeof closeReportModal === 'function') {
            closeReportModal();
        }
        closeAllDrawers();
        openPaymentDrawer();

        const select = document.querySelector('#paymentDrawer select[name="target_id"]');
        if (select) {
            select.value = targetId;
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }

        const typeSelect = document.getElementById('q-payment-type');
        if (typeSelect) {
            typeSelect.value = isJobWorker ? 'JOB_WORK' : 'SALARY';
            if (typeof toggleLoanFields === 'function') toggleLoanFields(typeSelect.value);
        }

        const initialMonth = '2026-09';
        populateSettlementMonths(initialMonth);

        currentDuesData = {
            targetId: targetId,
            targetName: targetName || '',
            monthlyDue: amount || 0,
            runningDue: amount || 0,
            isJobWorker: isJobWorker,
            selectedScope: 'MONTHLY',
            selectedMonth: initialMonth
        };

        const periodInput = document.getElementById('q-settlement-period');
        if (periodInput) periodInput.value = initialMonth;

        selectSettlementScope('MONTHLY');

        // Fetch real-time dues comparison
        fetch(`/api/labor/get-recipient-dues/?target_id=${encodeURIComponent(targetId)}&month=${initialMonth}`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    if (data.monthly_due > 0 || !amount) {
                        currentDuesData.monthlyDue = data.monthly_due;
                    } else if (amount && amount > 0) {
                        currentDuesData.monthlyDue = amount;
                    }
                    if (data.running_due > 0 || !amount) {
                        currentDuesData.runningDue = data.running_due;
                    } else if (amount && amount > 0) {
                        currentDuesData.runningDue = amount;
                    }
                    if (data.recipient_name) currentDuesData.targetName = data.recipient_name;
                    
                    const mSub = document.getElementById('scope-monthly-sub');
                    if (mSub) mSub.textContent = `Clears September 2026 (₹${currentDuesData.monthlyDue})`;
                    
                    const tSub = document.getElementById('scope-today-sub');
                    if (tSub) tSub.textContent = `Since last paid (₹${currentDuesData.runningDue})`;
                    
                    selectSettlementScope(currentDuesData.selectedScope);
                }
            })
            .catch(err => console.error("Error fetching recipient dues:", err));

        if (typeof updateRecipientLoanDeductionSection === 'function') {
            updateRecipientLoanDeductionSection();
        }
    }
    window.openQuickSettlementModal = openQuickSettlementModal;

    let isSavingPayment = false;
    async function savePayment(btn) {
        if (isSavingPayment) return;

        const form = document.getElementById('paymentForm');
        if (!form) return;

        const recipient = form.querySelector('[name="target_id"]')?.value;
        const amount = form.querySelector('[name="amount"]')?.value;

        if (!recipient) {
            alert("⚠️ Please select a Staff or Job Worker recipient.");
            return;
        }
        if (!amount || parseFloat(amount) <= 0) {
            alert("⚠️ Please enter a valid payment amount greater than ₹0.");
            return;
        }

        isSavingPayment = true;
        const submitBtn = btn || document.querySelector('#paymentDrawer button[onclick*="savePayment"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.dataset.origText = submitBtn.innerText;
            submitBtn.innerText = "Saving...";
        }

        const formData = new FormData(form);

        try {
            const response = await fetch("/api/payment/record/", {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'
                }
            });
            const data = await response.json();
            if (data.status === 'success') {
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Failed to record transaction'));
                isSavingPayment = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerText = submitBtn.dataset.origText || "CONFIRM TRANSACTION";
                }
            }
        } catch (err) {
            alert("Error saving transaction: " + err.message);
            isSavingPayment = false;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerText = submitBtn.dataset.origText || "CONFIRM TRANSACTION";
            }
        }
    }
    window.savePayment = savePayment;
