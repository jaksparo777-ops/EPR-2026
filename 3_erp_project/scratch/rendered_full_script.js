
;

;

;

;

;

    function showSection(section) {
        const sections = ['staff', 'jw', 'sheet'];
        for (var i = 0; i < sections.length; i++) {
            var s = sections[i];
            var sec = document.getElementById('section-' + s);
            var btn = document.getElementById('btn-' + s);
            if (sec) {
                if (s === section) {
                    sec.style.cssText = 'display: block !important;';
                    sec.classList.add('active');
                } else {
                    sec.style.cssText = 'display: none !important;';
                    sec.classList.remove('active');
                }
            }
            if (btn) {
                if (s === section) {
                    btn.classList.add('active');
                    btn.style.background = 'var(--accent-blue)';
                    btn.style.color = 'white';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = 'var(--text-secondary)';
                }
            }
        }

        try {
            sessionStorage.setItem('ledger_active_tab', section);
            const url = new URL(window.location);
            url.searchParams.set('tab', section);
            window.history.replaceState({}, '', url);
        } catch (e) {}
    }
    window.showSection = showSection;

    function changeLedgerMonth(val) {
        window.location.href = `?month=${val}`;
    }

    let activeEditingCell = null;
    let hoveredCell = null;
    let clickTimeout = null;
    let clickCount = 0;

    // Track active hovered cell for keyboard hotkeys
    function setHoveredCell(cell) {
        hoveredCell = cell;
    }

    function clearHoveredCell(cell) {
        if (hoveredCell === cell) {
            hoveredCell = null;
        }
    }

    // Keyboard Hotkey Listener
    document.addEventListener('keydown', async function(event) {
        if (!hoveredCell) return;
        
        // If the user is currently typing in an inline overtime input, ignore hotkeys
        if (document.activeElement && document.activeElement.classList.contains('inline-ot-input')) {
            return;
        }

        const key = event.key.toLowerCase();
        let newStatus = null;

        if (key === 'p') newStatus = 'PRESENT';
        else if (key === 'a') newStatus = 'ABSENT';
        else if (key === 'h') newStatus = 'HALF_DAY';
        else if (key === 'y') newStatus = 'HOLIDAY';
        else if (key === 'c' || event.key === 'Backspace' || event.key === 'Delete') newStatus = 'NONE';

        if (newStatus !== null) {
            event.preventDefault();
            const cell = hoveredCell;
            const workerId = cell.getAttribute('data-worker-id');
            const date = cell.getAttribute('data-date');
            const ot = cell.getAttribute('data-ot') || '0';

            // Visual feedback pulse instantly
            cell.classList.remove('success-pulse', 'error-pulse');
            
            try {
                const updated = await saveAttendanceState(workerId, newStatus, date, ot);
                if (updated) {
                    updateCellUI(cell, newStatus, ot);
                    cell.classList.add('success-pulse');
                } else {
                    cell.classList.add('error-pulse');
                }
            } catch (err) {
                console.error(err);
                cell.classList.add('error-pulse');
            }
        }
    });

    // Multi-click Detector & Inline OT Input trigger
    function handleCellClick(cell, event) {
        event.stopPropagation();
        
        // If an inline OT input is already active inside this cell, ignore additional clicks
        if (cell.querySelector('.inline-ot-input')) {
            return;
        }

        // Check current status
        const status = cell.getAttribute('data-status') || 'NONE';
        const ot = cell.getAttribute('data-ot') || '0';

        // 1. If status is PRESENT or HALF_DAY, clicking immediately enters inline overtime input!
        if (status === 'PRESENT' || status === 'HALF_DAY') {
            // Cancel any pending multi-click timer
            if (clickTimeout) {
                clearTimeout(clickTimeout);
                clickTimeout = null;
                clickCount = 0;
            }
            activateInlineOvertimeInput(cell);
            return;
        }

        // 2. Otherwise, detect multi-clicks (1, 2, or 3 clicks) to toggle status
        clickCount++;
        if (clickTimeout) {
            clearTimeout(clickTimeout);
        }

        clickTimeout = setTimeout(async () => {
            const currentClicks = clickCount;
            clickCount = 0;
            clickTimeout = null;

            let newStatus = 'NONE';
            if (currentClicks === 1) newStatus = 'PRESENT';
            else if (currentClicks === 2) newStatus = 'ABSENT';
            else if (currentClicks >= 3) newStatus = 'HALF_DAY';

            const workerId = cell.getAttribute('data-worker-id');
            const date = cell.getAttribute('data-date');

            cell.classList.remove('success-pulse', 'error-pulse');
            try {
                const updated = await saveAttendanceState(workerId, newStatus, date, ot);
                if (updated) {
                    updateCellUI(cell, newStatus, ot);
                    cell.classList.add('success-pulse');
                } else {
                    cell.classList.add('error-pulse');
                }
            } catch (err) {
                console.error(err);
                cell.classList.add('error-pulse');
            }
        }, 250); // 250ms window to detect double/triple click
    }

    // Activate the inline OT input directly inside the cell
    function activateInlineOvertimeInput(cell) {
        // Close any other open inline OT inputs first
        document.querySelectorAll('.inline-ot-input').forEach(input => {
            input.blur();
        });

        const statusContainer = cell.querySelector('.cell-status-container');
        const currentOt = cell.getAttribute('data-ot') || '0';

        // Save current HTML to restore in case of failure or blur
        const originalHTML = statusContainer.innerHTML;

        statusContainer.innerHTML = `<input type="number" step="0.5" min="0" max="24" class="inline-ot-input" value="${currentOt}">`;
        
        const input = statusContainer.querySelector('.inline-ot-input');
        input.focus();
        input.select();

        let isSaving = false;

        async function saveInlineOtValue() {
            if (isSaving) return;
            isSaving = true;

            const newOt = parseFloat(input.value || '0');
            const status = cell.getAttribute('data-status') || 'PRESENT';
            const workerId = cell.getAttribute('data-worker-id');
            const date = cell.getAttribute('data-date');

            cell.classList.remove('success-pulse', 'error-pulse');
            try {
                const updated = await saveAttendanceState(workerId, status, date, newOt);
                if (updated) {
                    cell.setAttribute('data-ot', newOt);
                    // Restore UI checkmark/symbol
                    updateCellUI(cell, status, newOt);
                    cell.classList.add('success-pulse');
                } else {
                    statusContainer.innerHTML = originalHTML;
                    cell.classList.add('error-pulse');
                }
            } catch (err) {
                console.error(err);
                statusContainer.innerHTML = originalHTML;
                cell.classList.add('error-pulse');
            }
        }

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur(); // Triggers saveInlineOtValue
            } else if (e.key === 'Escape') {
                e.preventDefault();
                isSaving = true; // prevent saving
                statusContainer.innerHTML = originalHTML; // restore
            }
        });

        input.addEventListener('blur', function() {
            saveInlineOtValue();
        });
    }

    // AJAX helper to submit attendance state changes
    async function saveAttendanceState(workerId, status, date, otHours) {
        const formData = new FormData();
        formData.append('worker_id', workerId);
        formData.append('status', status);
        formData.append('date', date);
        formData.append('ot_hours', otHours);
        formData.append('csrfmiddlewaretoken', 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW');

        try {
            const response = await fetch('/api/attendance/mark/', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            return data.status === 'success';
        } catch (err) {
            console.error(err);
            return false;
        }
    }

    // Helper to update grid cell visually in-place
    function updateCellUI(cell, status, ot) {
        cell.setAttribute('data-status', status);
        cell.setAttribute('data-ot', ot);

        const container = cell.querySelector('.cell-status-container');
        if (status === 'PRESENT') {
            container.innerHTML = '<span style="color:#10b981;">✓</span>';
        } else if (status === 'HALF_DAY') {
            container.innerHTML = '<span style="color:#f59e0b;">=</span>';
        } else if (status === 'ABSENT') {
            container.innerHTML = '<span style="color:#ef4444;">✕</span>';
        } else if (status === 'HOLIDAY') {
            container.innerHTML = '<span style="color:#fb923c; font-weight:800;">H</span>';
        } else {
            container.innerHTML = '<span style="color:var(--text-secondary); opacity:0.2;">·</span>';
        }

        const indicator = cell.querySelector('.cell-ot-indicator');
        const parsedOt = parseFloat(ot || '0');
        if (parsedOt > 0 && (status === 'PRESENT' || status === 'HALF_DAY')) {
            indicator.style.display = 'block';
            indicator.setAttribute('title', `OT: ${parsedOt}h`);
        } else {
            indicator.style.display = 'none';
        }
    }

    function switchTeam(team) {
        const params = new URLSearchParams(window.location.search);
        params.set('team', team);
        window.location.search = params.toString();
    }

    function openAttendanceDrawer(e) {
        if (e && e.preventDefault) e.preventDefault();
        closeAllDrawers();
        const drawer = document.getElementById('attendanceDrawer');
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
            loadAttendanceForDate();
        } catch(err) {
            console.error('Error loading attendance for date:', err);
        }
        return false;
    }

    async function loadAttendanceForDate() {
        const dateInput = document.getElementById('attendance-date-input');
        if (!dateInput) return;
        if (!dateInput.value) {
            const today = new Date();
            const yyyy = today.getFullYear();
            const mm = String(today.getMonth() + 1).padStart(2, '0');
            const dd = String(today.getDate()).padStart(2, '0');
            dateInput.value = `${yyyy}-${mm}-${dd}`;
        }
        const date = dateInput.value;

        const res = await fetch(`/api/attendance/fetch/?date=${date}`);
        const data = await res.json();
        const records = data.attendance || {};

        // Reset all to defaults first
        document.querySelectorAll('[id^="toggle-container-"]').forEach(container => {
            const workerId = container.id.replace('toggle-container-', '');
            const record = records[workerId];

            // Reset UI
            container.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            const statusInput = document.getElementById('input-' + workerId);
            const otInput = document.querySelector(`input[name="ot_${workerId}"]`);

            if (record) {
                // Load existing
                statusInput.value = record.status;
                otInput.value = record.ot;
                const btnEl = container.querySelector(`.toggle-btn.${btnClass}`);
                if (btnEl) btnEl.classList.add('active');
            } else {
                // Default to Present
                if (statusInput) statusInput.value = 'PRESENT';
                if (otInput) otInput.value = 0;
                const btnEl = container.querySelector('.toggle-btn.present');
                if (btnEl) btnEl.classList.add('active');
            }
        });
    }

    const recipientLoanMap = {
        
        "w_13": 0,
        
        "w_14": 0,
        
        "w_15": 0,
        
        "w_16": 0,
        
        "w_17": 0,
        
        "w_18": 0,
        
        "w_19": 0,
        
        "w_34": 0,
        
        
        "jw_9": 0,
        
        "jw_10": 0,
        
        "jw_17": 0,
        
        "jw_27": 18000.0,
        
        "jw_28": 0,
        
        "jw_29": 5000.0,
        
        "jw_30": 0,
        
        "jw_31": 0,
        
        "jw_32": 0,
        
        "jw_33": 0,
        
        "jw_34": 0,
        
        "jw_35": 0,
        
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

    function openPaymentDrawer(e) {
        if (e && e.preventDefault) e.preventDefault();
        closeAllDrawers();
        const drawer = document.getElementById('paymentDrawer');
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
            updateRecipientLoanDeductionSection();
        } catch(err) {
            console.error('Error updating payment loan deduction section:', err);
        }
        return false;
    }
    window.openPaymentDrawer = openPaymentDrawer;

    function closePaymentDrawer() {
        const backdrop = document.getElementById('drawerBackdrop');
        const drawer = document.getElementById('paymentDrawer');
        if (backdrop) {
            backdrop.style.setProperty('display', 'none', 'important');
            backdrop.classList.remove('active');
        }
        if (drawer) {
            drawer.style.setProperty('right', '-100vw', 'important');
            drawer.classList.remove('active');
        }
    }
    window.closePaymentDrawer = closePaymentDrawer;

    function closeAllDrawers() {
        const backdrop = document.getElementById('drawerBackdrop');
        if (backdrop) {
            backdrop.style.setProperty('display', 'none', 'important');
            backdrop.classList.remove('active');
        }
        document.querySelectorAll('.drawer').forEach(d => {
            d.style.setProperty('right', '-100vw', 'important');
            d.classList.remove('active');
        });
        currentProfileWorkerId = null;
    }

    let currentDuesData = {
        targetId: null,
        targetName: '',
        monthlyDue: 0,
        runningDue: 0,
        isJobWorker: false,
        selectedScope: 'MONTHLY',
        selectedMonth: '2026-08'
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

    function onSettlementMonthChange(monthVal) {
        document.getElementById('q-settlement-period').value = monthVal;
        currentDuesData.selectedMonth = monthVal;
        
        fetch(`/api/labor/get-recipient-dues/?target_id=${encodeURIComponent(currentDuesData.targetId)}&month=${monthVal}`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    currentDuesData.monthlyDue = data.monthly_due;
                    const sel = document.getElementById('scope-target-month');
                    const selText = sel ? sel.options[sel.selectedIndex].text.split('(')[0].trim() : monthVal;
                    
                    const mSub = document.getElementById('scope-monthly-sub');
                    if (mSub) mSub.textContent = `Clears ${selText} (₹${data.monthly_due})`;
                    
                    selectSettlementScope('MONTHLY');
                }
            })
            .catch(err => console.error("Error changing settlement month:", err));
    }

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
                const selText = sel ? sel.options[sel.selectedIndex].text.split('(')[0].trim() : currentDuesData.selectedMonth;
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
        recalculateSplitPayout();
    }

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

        const initialMonth = '2026-08';
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
                    if (mSub) mSub.textContent = `Clears August 2026 (₹${currentDuesData.monthlyDue})`;
                    
                    const tSub = document.getElementById('scope-today-sub');
                    if (tSub) tSub.textContent = `Since last paid (₹${currentDuesData.runningDue})`;
                    
                    selectSettlementScope(currentDuesData.selectedScope);
                }
            })
            .catch(err => console.error("Error fetching recipient dues:", err));

        updateRecipientLoanDeductionSection();
    }

    // JOB WORKER PROFILE LOGIC
    let currentProfileWorkerId = null;
    let drawerCurrentMode = 'monthly';
    let drawerCurrentMonth = '2026-08';
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
            console.error(err);
        }
    }

    async function openJobWorkerProfile(id) {
        closeAllDrawers();
        currentProfileWorkerId = id;
        drawerCurrentMode = 'monthly';
        drawerCurrentMonth = '2026-08';
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
                drawerMonthPicker.setDate('2026-08', false);
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

            resetRateRowsContainer();
            showProfileTab('history');
        } catch (err) {
            console.error('Error preparing profile drawer UI:', err);
        }

        loadJobWorkerProfileLedger();
    }
    window.openJobWorkerProfile = openJobWorkerProfile;

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
            (data.items || []).forEach(item => {
                const tr = document.createElement('tr');
                tr.style.borderBottom = '1px solid var(--border-soft)';
                tr.innerHTML = `
                    <td style="padding:10px; font-size:13px;">${item.item_name}</td>
                    <td style="padding:10px; text-align:right; font-weight:bold;">₹${parseFloat(item.rate || 0).toFixed(2)}</td>
                    <td style="padding:10px; text-align:right;">
                        <button onclick="removeAllocation('${item.id}')" style="background:none; border:none; color:#ef4444; cursor:pointer;">✕</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
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

        // Dynamic Calendar View for Casting job workers
        const calContainer = document.getElementById('profile-history-calendar-container');
        const ledgerTable = document.getElementById('profile-ledger-table');
        const titleH3 = document.getElementById('profile-history-title');

        if (data.process === 'casting' && data.calendar_weeks) {
            ledgerTable.style.display = 'none';
            calContainer.style.display = 'block';
            titleH3.innerText = `CASTING WORK & EARNINGS - ${data.month_name}`;

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
                    .drawer-tooltip-content {
                        display: none;
                        position: absolute;
                        bottom: 110%;
                        left: 50%;
                        transform: translateX(-50%);
                        background: #1e293b;
                        color: #f1f5f9;
                        padding: 6px 10px;
                        border-radius: 6px;
                        font-size: 10px;
                        white-space: nowrap;
                        z-index: 1000;
                        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
                        border: 1px solid rgba(255,255,255,0.08);
                    }
                    .tooltip-trigger:hover .drawer-tooltip-content {
                        display: block;
                    }
                    .drawer-tooltip-content::after {
                        content: "";
                        position: absolute;
                        top: 100%;
                        left: 50%;
                        margin-left: -4px;
                        border-width: 4px;
                        border-style: solid;
                        border-color: #1e293b transparent transparent transparent;
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
                        if (isWork && day.details && day.details.length > 0) cellClasses.push('tooltip-trigger');

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

                        if (isWork && day.details && day.details.length > 0) {
                            html += `
                                <div class="drawer-tooltip-content">
                                    <div style="font-weight: bold; margin-bottom: 2px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 2px;">Items Breakdown:</div>
                            `;
                            day.details.forEach(item => {
                                html += `
                                    <div style="display: flex; justify-content: space-between; gap: 10px;">
                                        <span>${item.item_key}</span>
                                        <span style="font-weight: bold; color: var(--accent-blue);">${item.weight.toFixed(1)} kg</span>
                                    </div>
                                `;
                            });
                            html += `</div>`;
                        }

                        html += `</div>`;
                    } else {
                        html += `<div class="drawer-cal-cell" style="opacity: 0.15; border-style: dashed;"></div>`;
                    }
                });
            });

            html += `</div>`;
            
            calContainer.innerHTML = html;
        } else {
            calContainer.style.display = 'none';
            ledgerTable.style.display = 'table';
            titleH3.innerText = "RECENT TRANSACTIONS";
        }
    }

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

    function closeJobWorkerProfile() {
        document.getElementById('jobWorkerProfileDrawer').classList.remove('active');
        document.getElementById('drawerBackdrop').classList.remove('active');
    }

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
            <input type="number" id="rate-input-${rowId}" value="${defaultRate}" step="0.01" placeholder="Rate ₹" style="width:110px; background:#1e293b; color:white; border:1px solid var(--border-soft); padding:8px 10px; border-radius:8px; font-weight:bold; font-size:13px;">
            <button type="button" onclick="removeRateRow(${rowId})" style="background:rgba(239, 68, 68, 0.15); color:#f87171; border:1px solid rgba(239, 68, 68, 0.3); padding:8px 12px; border-radius:8px; cursor:pointer; font-weight:bold; font-size:12px;" title="Remove row">✕</button>
        `;

        container.appendChild(div);

        const selectEl = document.getElementById(`rate-item-select-${rowId}`);
        if (selectEl && typeof TomSelect !== 'undefined') {
            rateTomSelects[rowId] = new TomSelect(selectEl, {
                create: false,
                placeholder: 'Type & search item code or name...',
                maxOptions: 1000,
                sortField: { field: 'text', direction: 'asc' }
            });
            if (defaultItemId) {
                rateTomSelects[rowId].setValue(defaultItemId);
            }
        }
    }

    function viewSettledVoucher(workerId, name, amount, monthName) {
        alert("📜 SETTLEMENT VOUCHER ARCHIVE\n-----------------------------------\nWorker / Unit: " + name + "\nMonth: " + monthName + "\nSettlement Amount Cleared: ₹" + amount + "\nStatus: CLOSED & ARCHIVED (Clean Slate Reset Active)\n-----------------------------------\nAll accounts for this cycle have been 100% settled.");
    }

    function removeRateRow(rowId) {
        if (rateTomSelects[rowId]) {
            rateTomSelects[rowId].destroy();
            delete rateTomSelects[rowId];
        }
        const el = document.getElementById(`rate-row-${rowId}`);
        if (el) el.remove();
        
        const container = document.getElementById('rate-rows-container');
        if (container && container.children.length === 0) {
            addRateRow();
        }
    }

    async function saveAllWorkerRates() {
        const allocations = [];
        
        Object.keys(rateTomSelects).forEach(rowId => {
            const ts = rateTomSelects[rowId];
            const itemId = ts ? ts.getValue() : '';
            const rateInput = document.getElementById(`rate-input-${rowId}`);
            const rate = rateInput ? rateInput.value : '';

            if (itemId && rate !== '' && rate !== null && !isNaN(rate) && parseFloat(rate) >= 0) {
                allocations.push({ item_id: itemId, rate: rate });
            }
        });

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
                headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
            });
            const data = await res.json();
            if (data.status === 'success') {
                resetRateRowsContainer();
                openJobWorkerProfile(currentProfileWorkerId);
            } else {
                alert('⚠️ ' + (data.error || 'Failed to save item rates'));
            }
        } catch (err) {
            console.error(err);
            alert('⚠️ Network error saving item rates');
        }
    }

    async function removeAllocation(id) {
        if (!confirm('Remove this allocation?')) return;
        const res = await fetch(`/api/allocation/${id}/delete/`, {
            method: 'POST',
            headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
        });
        const data = await res.json();
        if (data.status === 'success') openJobWorkerProfile(currentProfileWorkerId);
    }

    function setAttendance(btn, status, workerId) {
        const container = document.getElementById('toggle-container-' + workerId);
        container.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('input-' + workerId).value = status;
    }

    async function saveAttendance() {
        const form = document.getElementById('attendanceForm');
        const formData = new FormData(form);
        
        // Find all hidden status inputs to know which workers are being processed
        const entries = [];
        form.querySelectorAll('input[name^="status_"]').forEach(input => {
            const workerId = input.name.replace('status_', '');
            const status = input.value;
            const ot = form.querySelector(`input[name="ot_${workerId}"]`).value;
            entries.push({worker_id: workerId, status: status, ot: ot});
        });

        for (let entry of entries) {
            const fd = new FormData();
            fd.append('worker_id', entry.worker_id);
            fd.append('status', entry.status);
            fd.append('ot_hours', entry.ot);
            fd.append('date', formData.get('date'));
            
            await fetch('/api/attendance/mark/', {
                method: 'POST',
                body: fd,
                headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
            });
        }
        location.reload();
    }

    async function savePayment() {
        const form = document.getElementById('paymentForm');
        const formData = new FormData(form);

        try {
            const response = await fetch('/api/payment/record/', {
                method: 'POST',
                body: formData,
                headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
            });
            const data = await response.json();
            if (data.status === 'success') {
                location.reload();
            } else {
                alert(data.error);
            }
        } catch (e) {
            console.error(e);
        }
    }
    // --- INTERNAL WORKER PROFILE ---
    function openWorkerProfile(id) {
        closeAllDrawers();
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
        
        const currentMonth = '2026-08';
        const link = document.getElementById('worker-report-link');
        if (link) link.href = `/worker/${id}/report/?month=${currentMonth}`;
        
        fetch(`/api/worker/${id}/profile/`)
            .then(r => r.json())
            .then(data => {
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
                
                const stats = data.stats || {};
                setTxt('worker-stat-earned', '₹' + (stats.earned || 0));
                setTxt('worker-stat-paid', '₹' + (stats.paid || 0));
                setTxt('worker-stat-balance', '₹' + (stats.balance || 0));
                
                // Update Monthly Stats
                setTxt('stat-days-present', stats.present || 0);
                setTxt('stat-days-half', stats.half || 0);
                setTxt('stat-days-absent', stats.absent || 0);

                // Render Calendar
                renderAttendanceCalendar(data);
                
                // Payments
                const payBody = document.getElementById('worker-payment-body');
                if (payBody) {
                    payBody.innerHTML = (data.payments || []).map(p => {
                        let actionsHtml = '';
                        
                        const pType = p.raw_type || p.type || 'ADVANCE';
                        const pMode = p.mode || 'CASH';
                        const pDate = p.raw_date || p.date;
                        actionsHtml = `
                            <td style="padding:6px 10px; text-align:right; white-space:nowrap;">
                                <button type="button" onclick="openEditPaymentModal(${p.id}, '${pDate}', ${p.amount}, '${pType}', '${pMode}')" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer; margin-right:4px;">✏️ EDIT</button>
                                <button type="button" onclick="deletePayment(${p.id}, ${p.amount})" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer;">🗑️ DELETE</button>
                            </td>
                        `;
                        
                        return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                            <td style="padding:10px; font-size:12px;">${p.date}</td>
                            <td style="padding:10px; font-size:11px; text-transform:uppercase; color:var(--text-secondary);">${p.mode}</td>
                            <td style="padding:10px; text-align:right; font-weight:bold;">₹${p.amount}</td>
                            ${actionsHtml}
                        </tr>`;
                    }).join('') || '<tr><td colspan="4" style="text-align:center; padding:20px; color:var(--text-secondary);">No records</td></tr>';
                }
                
                showWorkerTab('attendance');
            })
            .catch(err => console.error("Error loading worker profile:", err));
    }
    window.openWorkerProfile = openWorkerProfile;

    function renderAttendanceCalendar(data) {
        const grid = document.getElementById('attendance-calendar-grid');
        grid.innerHTML = '';
        
        const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        document.getElementById('calendar-month-name').innerText = `${monthNames[data.month-1]} ${data.year}`;

        // Header for weekdays
        ['S','M','T','W','T','F','S'].forEach(day => {
            const el = document.createElement('div');
            el.style = "text-align:center; font-size:10px; color:var(--text-secondary); padding-bottom:5px; font-weight:bold;";
            el.innerText = day;
            grid.appendChild(el);
        });

        const firstDay = new Date(data.year, data.month - 1, 1).getDay();
        const daysInMonth = new Date(data.year, data.month, 0).getDate();

        // Map attendance by date string
        const attMap = {};
        data.attendance.forEach(a => attMap[a.raw_date] = a);

        // Fill empty slots before 1st
        for(let i=0; i < firstDay; i++) {
            grid.appendChild(document.createElement('div'));
        }

        // Fill dates
        for(let d=1; d <= daysInMonth; d++) {
            const dateStr = `${data.year}-${String(data.month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
            const record = attMap[dateStr];
            
            const cell = document.createElement('div');
            cell.style = `
                aspect-ratio: 1;
                background: rgba(255,255,255,0.03);
                border-radius: 8px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                border: 1px solid ${record ? 'rgba(255,255,255,0.1)' : 'var(--border-soft)'};
                position: relative;
            `;

            const dateNum = document.createElement('span');
            dateNum.style = "font-size:11px; font-weight:bold; color:var(--text-secondary);";
            dateNum.innerText = d;
            cell.appendChild(dateNum);

            if (record) {
                const symbol = document.createElement('div');
                let color = "#10b981"; // Present
                let icon = "✓";
                if (record.raw_status === 'ABSENT') { color = "#ef4444"; icon = "✕"; }
                else if (record.raw_status === 'HALF_DAY') { color = "#f59e0b"; icon = "="; }
                
                symbol.style = `font-size:14px; font-weight:bold; color:${color}; margin-top:2px;`;
                symbol.innerText = icon;
                cell.appendChild(symbol);

                if (record.ot > 0) {
                    const otIndicator = document.createElement('div');
                    otIndicator.style = "position:absolute; top:2px; right:2px; width:4px; height:4px; background:var(--accent-blue); border-radius:50%;";
                    otIndicator.title = `OT: ${record.ot}h`;
                    cell.appendChild(otIndicator);
                }
            }

            grid.appendChild(cell);
        }
    }

    function toggleLoanFields(val) {
        const emiBox = document.getElementById('q-emi-box');
        const amountLabel = document.getElementById('label-amount');
        
        if (val === 'NEW_LOAN') {
            emiBox.style.display = 'block';
            amountLabel.innerText = "Total Loan Amount (₹)";
        } else {
            emiBox.style.display = 'none';
            amountLabel.innerText = "Amount (₹)";
        }
    }

    let isSavingPayment = false;
    function savePayment(btn) {
        if (isSavingPayment) return;

        const form = document.getElementById('paymentForm');
        const recipient = form.querySelector('[name="target_id"]').value;
        const amount = form.querySelector('[name="amount"]').value;

        if (!recipient) {
            alert("⚠️ Please select a Staff or Job Worker recipient.");
            return;
        }
        if (!amount || parseFloat(amount) <= 0) {
            alert("⚠️ Please enter a valid payment amount greater than ₹0.");
            return;
        }

        isSavingPayment = true;
        const submitBtn = btn || form.querySelector('button[type="submit"], button[onclick*="savePayment"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.dataset.origText = submitBtn.innerText;
            submitBtn.innerText = "Saving...";
        }

        const formData = new FormData(form);
        
        fetch("/api/payment/record/", {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Failed to record transaction'));
                isSavingPayment = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerText = submitBtn.dataset.origText || "SAVE PAYMENT";
                }
            }
        })
        .catch(err => {
            alert("Error saving transaction: " + err.message);
            isSavingPayment = false;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerText = submitBtn.dataset.origText || "SAVE PAYMENT";
            }
        });
    }

    function quickLoanRepayment(workerId, emiAmount) {
        if (!confirm(`Record EMI payment of ₹${emiAmount}?`)) return;
        
        const formData = new FormData();
        formData.append('target_id', 'w_' + workerId);
        formData.append('amount', emiAmount);
        formData.append('payment_type', 'LOAN_REPAYMENT');
        formData.append('payment_mode', 'CASH');
        formData.append('notes', 'Monthly EMI repayment (Quick)');
        formData.append('csrfmiddlewaretoken', 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW');

        fetch("/api/payment/record/", {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                location.reload();
            } else {
                alert('Error recording repayment: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(err => {
            alert("Error recording repayment: " + err.message);
        });
    }

    function closeWorkerProfile() {
        document.getElementById('workerProfileDrawer').classList.remove('active');
        document.getElementById('drawerBackdrop').classList.remove('active');
    }

    function showWorkerTab(tab) {
        document.querySelectorAll('.w-tab-content').forEach(c => c.style.display = 'none');
        const contentEl = document.getElementById('w-content-' + tab);
        if (contentEl) contentEl.style.display = 'block';
        
        const attTab = document.getElementById('w-tab-attendance');
        const pmtTab = document.getElementById('w-tab-payments');
        if (attTab) {
            attTab.style.borderBottom = tab === 'attendance' ? '2px solid var(--accent-blue)' : 'none';
            attTab.style.color = tab === 'attendance' ? 'var(--accent-blue)' : 'var(--text-secondary)';
        }
        if (pmtTab) {
            pmtTab.style.borderBottom = tab === 'payments' ? '2px solid var(--accent-blue)' : 'none';
            pmtTab.style.color = tab === 'payments' ? 'var(--accent-blue)' : 'var(--text-secondary)';
        }
    }


;

    document.addEventListener('DOMContentLoaded', function() {
        const btnStaff = document.getElementById('btn-staff');
        const btnJw = document.getElementById('btn-jw');
        const btnSheet = document.getElementById('btn-sheet');

        if (btnStaff) btnStaff.addEventListener('click', function(e) { showSection('staff'); });
        if (btnJw) btnJw.addEventListener('click', function(e) { showSection('jw'); });
        if (btnSheet) btnSheet.addEventListener('click', function(e) { showSection('sheet'); });

        const targetSelect = document.querySelector('#paymentDrawer select[name="target_id"]');
        if (targetSelect) {
            targetSelect.addEventListener('change', function() {
                updateRecipientLoanDeductionSection();
            });
        }

        // Server-Side Auto-Open Drawer Fallback
        
    });

    // Initialize Flatpickr for the attendance date
    if (typeof flatpickr !== 'undefined' && document.getElementById('attendance-date-input')) {
        flatpickr("#attendance-date-input", {
            altInput: true,
            altFormat: "j/n/Y",
            dateFormat: "Y-m-d",
            defaultDate: "today",
            theme: "dark",
            onChange: function(selectedDates, dateStr, instance) {
                loadAttendanceForDate();
            }
        });
    }

    // Initialize Flatpickr for Month Picker
    if (typeof flatpickr !== 'undefined' && document.getElementById('ledger-month-picker')) {
        const monthPlugins = [];
        if (typeof monthSelectPlugin !== 'undefined') {
            monthPlugins.push(new monthSelectPlugin({
                shorthand: true,
                dateFormat: "Y-m",
                altFormat: "F Y",
                theme: "dark"
            }));
        }
        flatpickr("#ledger-month-picker", {
            plugins: monthPlugins,
            defaultDate: "2026-08",
            onChange: function(selectedDates, dateStr, instance) {
                changeLedgerMonth(dateStr);
            }
        });
    }

    // Initialize Flatpickr for Drawer Month Picker
    if (typeof flatpickr !== 'undefined' && document.getElementById('drawer-month-picker')) {
        const drawerMonthPlugins = [];
        if (typeof monthSelectPlugin !== 'undefined') {
            drawerMonthPlugins.push(new monthSelectPlugin({
                shorthand: true,
                dateFormat: "Y-m",
                altFormat: "F Y",
                theme: "dark"
            }));
        }
        drawerMonthPicker = flatpickr("#drawer-month-picker", {
            plugins: drawerMonthPlugins,
            defaultDate: "2026-08",
            onChange: function(selectedDates, dateStr, instance) {
                drawerCurrentMonth = dateStr;
                drawerCurrentMode = 'monthly';
                const modeSelect = document.getElementById('drawer-mode-selector');
                if (modeSelect) modeSelect.value = 'monthly';
                loadJobWorkerProfileLedger();
            }
        });
    }

    // Initialize Flatpickr for Quick Cash Outflow Date
    function updateQDateBadge(dateObj) {
        if (!dateObj) return;
        const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
        const mEl = document.getElementById('q-date-month');
        const dEl = document.getElementById('q-date-day');
        if (mEl) mEl.textContent = months[dateObj.getMonth()];
        if (dEl) dEl.textContent = dateObj.getDate();
    }

    if (typeof flatpickr !== 'undefined' && document.getElementById('q-payment-date')) {
        flatpickr("#q-payment-date", {
            altInput: true,
            altFormat: "j/n/Y",
            dateFormat: "Y-m-d",
            defaultDate: "today",
            theme: "dark",
            onReady: function(selectedDates, dateStr, instance) {
                if (selectedDates[0]) updateQDateBadge(selectedDates[0]);
                if (instance.altInput) {
                    instance.altInput.style.paddingLeft = '48px';
                }
            },
            onChange: function(selectedDates, dateStr, instance) {
                if (selectedDates[0]) updateQDateBadge(selectedDates[0]);
            }
        });
    }

;

    function filterStaffTable(mode, btnEl) {
        document.querySelectorAll('.staff-f-btn').forEach(b => {
            b.classList.remove('active');
            b.style.background = 'transparent';
            if (b.getAttribute('onclick').includes('FULLY_PAID')) {
                b.style.color = '#34d399';
            } else if (b.getAttribute('onclick').includes('PENDING')) {
                b.style.color = '#ef4444';
            } else {
                b.style.color = '#cbd5e1';
            }
        });
        btnEl.classList.add('active');
        btnEl.style.background = 'var(--accent-blue)';
        btnEl.style.color = 'white';

        const rows = document.querySelectorAll('#staff-table tbody tr');
        rows.forEach(row => {
            const st = row.getAttribute('data-status-code');
            if (mode === 'ALL') {
                row.style.display = '';
            } else if (mode === 'FULLY_PAID') {
                row.style.display = (st === 'FULLY_PAID') ? '' : 'none';
            } else if (mode === 'PENDING') {
                row.style.display = (st === 'PARTIAL' || st === 'PENDING') ? '' : 'none';
            }
        });
    }

    function filterJwTable(mode, btnEl) {
        document.querySelectorAll('.jw-f-btn').forEach(b => {
            b.classList.remove('active');
            b.style.background = 'transparent';
            if (b.getAttribute('onclick').includes('FULLY_PAID')) {
                b.style.color = '#34d399';
            } else if (b.getAttribute('onclick').includes('PENDING')) {
                b.style.color = '#ef4444';
            } else {
                b.style.color = '#cbd5e1';
            }
        });
        btnEl.classList.add('active');
        btnEl.style.background = 'var(--accent-blue)';
        btnEl.style.color = 'white';

        const rows = document.querySelectorAll('#jw-table tbody tr');
        rows.forEach(row => {
            const st = row.getAttribute('data-status-code');
            if (mode === 'ALL') {
                row.style.display = '';
            } else if (mode === 'FULLY_PAID') {
                row.style.display = (st === 'FULLY_PAID') ? '' : 'none';
            } else if (mode === 'PENDING') {
                row.style.display = (st === 'PARTIAL' || st === 'PENDING') ? '' : 'none';
            }
        });
    }

    const allStaffMembers = [
        
        { id: "13", name: "Anand" },
        
        { id: "14", name: "Sur.p" },
        
        { id: "15", name: "Mistri" },
        
        { id: "16", name: "Rekha.b" },
        
        { id: "17", name: "Madhu.b" },
        
        { id: "18", name: "Gauri.b" },
        
        { id: "19", name: "Paras" },
        
        { id: "34", name: "Naval Bhai" },
        
    ];

    const allJobWorkers = [
        
        { id: "9", name: "Gov/Gop" },
        
        { id: "10", name: "Pip Cutting" },
        
        { id: "17", name: "Ratan" },
        
        { id: "27", name: "Kailash bhai" },
        
        { id: "28", name: "Ramesh bhai" },
        
        { id: "29", name: "Mehul bhai" },
        
        { id: "30", name: "Tarkeshwar bhai" },
        
        { id: "31", name: "Jaynti bhai" },
        
        { id: "32", name: "Anand bhai" },
        
        { id: "33", name: "Sap Vab/Kam/Mnk" },
        
        { id: "34", name: "Mahadev Dasta" },
        
        { id: "35", name: "Forging handle" },
        
    ];

    async function compileBulkPDFs(items, isJobWorker) {
        const modal = document.getElementById('bulkDownloadModal');
        const progressText = document.getElementById('bulkProgressText');
        const progressBar = document.getElementById('bulkProgressBar');
        const currentMonth = "2026-08";

        if (!items || items.length === 0) {
            alert("No entries to download.");
            return;
        }

        // Show modal
        modal.style.setProperty('display', 'flex', 'important');
        progressBar.style.width = '0%';
        progressBar.style.background = isJobWorker ? '#3b82f6' : '#10b981';

        const zip = new JSZip();

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const pct = Math.round((i / items.length) * 100);
            progressText.innerText = `Generating PDF for ${item.name} (${i + 1} of ${items.length})...`;
            progressBar.style.width = `${pct}%`;

            try {
                const url = isJobWorker 
                    ? `/ledger/job-worker/${item.id}/report/?month=${currentMonth}`
                    : `/worker/${item.id}/report/?month=${currentMonth}`;
                
                const response = await fetch(url);
                const htmlText = await response.text();

                const parser = new DOMParser();
                const doc = parser.parseFromString(htmlText, 'text/html');
                const container = doc.querySelector('.slip-container');

                if (!container) {
                    console.error(`Could not find slip container for ${item.name}`);
                    continue;
                }

                // Apply 100% pure solid B&W print styles to the container
                container.classList.add('pdf-print-mode');

                // Copy report's own style blocks into the container so it renders with correct fonts/layout
                const styles = doc.querySelectorAll('style');
                styles.forEach(s => container.appendChild(s.cloneNode(true)));

                const opt = {
                    margin:       [3, 3, 3, 3],
                    image:        { type: 'jpeg', quality: 0.98 },
                    html2canvas:  { scale: 2, useCORS: true, logging: false },
                    jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
                    pagebreak:    { mode: 'avoid-all' }
                };

                const pdfBlob = await html2pdf().set(opt).from(container).output('blob');
                const safeName = item.name.replace(/\s+/g, '_');
                const fileName = isJobWorker 
                    ? `JobWorker_Statement_${safeName}_${currentMonth}.pdf`
                    : `Salary_Slip_${safeName}_${currentMonth}.pdf`;
                
                zip.file(fileName, pdfBlob);
            } catch (err) {
                console.error(`Failed to compile PDF for ${item.name}:`, err);
            }
        }

        progressText.innerText = "Packing ZIP file...";
        progressBar.style.width = '100%';

        try {
            const content = await zip.generateAsync({ type: "blob" });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(content);
            const zipName = isJobWorker
                ? `JobWorker_Statements_${currentMonth}.zip`
                : `Salary_Slips_${currentMonth}.zip`;
            link.download = zipName;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (err) {
            console.error("Failed to generate ZIP:", err);
            alert("Failed to package ZIP archive.");
        } finally {
            modal.style.setProperty('display', 'none', 'important');
        }
    }

    function downloadAllStaffPDFs() {
        compileBulkPDFs(allStaffMembers, false);
    }

    function downloadAllJwPDFs() {
        compileBulkPDFs(allJobWorkers, true);
    }

    function openReportModal() {
        if (!currentProfileWorkerId) return;
        const currentMonth = "2026-08";
        const iframe = document.getElementById('inlineStatementIframe');
        iframe.src = `/ledger/job-worker/${currentProfileWorkerId}/report/?month=${currentMonth}`;
        if (typeof closeJobWorkerProfile === 'function') {
            closeJobWorkerProfile();
        }
        document.getElementById('inlineStatementModal').style.display = 'flex';
    }

    function closeReportModal() {
        const iframe = document.getElementById('inlineStatementIframe');
        iframe.src = '';
        document.getElementById('inlineStatementModal').style.display = 'none';
    }

    function deletePayment(paymentId, amount) {
        if (!confirm(`Are you sure you want to delete this payment transaction of ₹${amount}?`)) return;
        
        fetch(`/api/payment/${paymentId}/delete/`, {
            method: 'POST',
            headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                if (currentProfileWorkerId) {
                    loadJobWorkerProfileLedger();
                } else {
                    location.reload();
                }
            } else {
                alert('Error: ' + (data.error || 'Failed to delete payment'));
            }
        });
    }

    function deleteStockTx(txId, desc) {
        if (!confirm(`Are you sure you want to delete stock transaction "${desc}"?`)) return;
        
        fetch(`/api/stock-transaction/${txId}/delete/`, {
            method: 'POST',
            headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                if (currentProfileWorkerId) {
                    loadJobWorkerProfileLedger();
                } else {
                    location.reload();
                }
            } else {
                alert('Error: ' + (data.error || 'Failed to delete stock transaction'));
            }
        });
    }

    function toggleSelectAllTx(masterCheck) {
        const checkboxes = document.querySelectorAll('.tx-select-checkbox');
        checkboxes.forEach(cb => {
            if (cb.offsetParent !== null) {
                cb.checked = masterCheck.checked;
            }
        });
        updateBulkDeleteTxButton();
    }

    function updateBulkDeleteTxButton() {
        const selected = document.querySelectorAll('.tx-select-checkbox:checked');
        const countSpan = document.getElementById('selectedTxCount');
        const bulkBtn = document.getElementById('btn-bulk-delete-tx');
        const masterCheck = document.getElementById('selectAllTxCheckbox');
        
        if (countSpan) countSpan.textContent = selected.length;
        if (bulkBtn) {
            bulkBtn.style.display = selected.length > 0 ? 'inline-flex' : 'none';
        }
        
        const allVisible = document.querySelectorAll('.tx-select-checkbox');
        if (masterCheck && allVisible.length > 0) {
            masterCheck.checked = (selected.length === allVisible.length);
        }
    }

    async function bulkDeleteSelectedTx() {
        const selected = document.querySelectorAll('.tx-select-checkbox:checked');
        if (selected.length === 0) return;

        const items = Array.from(selected).map(cb => ({
            id: parseInt(cb.getAttribute('data-tx-id')),
            type: cb.getAttribute('data-entry-type') || 'TX'
        }));

        if (!confirm(`Are you sure you want to delete ${items.length} selected transaction(s)?\n\nStock balances will be automatically restored/reversed back to their source locations.`)) {
            return;
        }

        try {
            const response = await fetch('/api/stock-transaction/bulk-delete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'
                },
                body: JSON.stringify({ items: items })
            });
            const data = await response.json();
            if (data.status === 'success') {
                if (currentProfileWorkerId) {
                    loadJobWorkerProfileLedger();
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

    let editPaymentPicker = null;

    function openEditPaymentModal(id, date, amount, type, mode) {
        document.getElementById('edit-payment-id').value = id;
        document.getElementById('edit-payment-amount').value = amount;
        document.getElementById('edit-payment-type').value = type;
        document.getElementById('edit-payment-mode').value = mode;

        if (!editPaymentPicker) {
            editPaymentPicker = flatpickr("#edit-payment-date", {
                altInput: true,
                altFormat: "j/n/Y",
                dateFormat: "Y-m-d",
                theme: "dark"
            });
        }
        editPaymentPicker.setDate(date || "today");

        const modal = document.getElementById('editPaymentModal');
        modal.style.display = 'flex';
    }

    function closeEditPaymentModal() {
        document.getElementById('editPaymentModal').style.display = 'none';
    }

    function submitEditPayment() {
        const id = document.getElementById('edit-payment-id').value;
        const form = document.getElementById('editPaymentForm');
        const formData = new FormData(form);

        fetch(`/api/payment/${id}/edit/`, {
            method: 'POST',
            body: formData,
            headers: {'X-CSRFToken': 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW'}
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                closeEditPaymentModal();
                if (currentProfileWorkerId) {
                    loadJobWorkerProfileLedger();
                } else {
                    location.reload();
                }
            } else {
                alert('Error: ' + (data.error || 'Failed to update payment'));
            }
        });
    }

    // Trigger action drawer from global search url queries on load & restore active tab
    function initLedgerTabAndAction() {
        const params = new URLSearchParams(window.location.search);
        const savedTab = params.get('tab') || sessionStorage.getItem('ledger_active_tab');
        if (savedTab && ['staff', 'jw', 'sheet'].includes(savedTab)) {
            showSection(savedTab);
        }

        const drawerParam = params.get('drawer');
        if (drawerParam === 'attendance') {
            setTimeout(openAttendanceDrawer, 300);
        } else if (drawerParam === 'payment') {
            setTimeout(openPaymentDrawer, 300);
        }

        const action = params.get('action');
        const targetId = params.get('target_id');
        const urlAmount = params.get('amount');
        const urlType = params.get('payment_type') || params.get('type');
        const urlNotes = params.get('notes');
        
        if (action === 'payment' && targetId) {
            setTimeout(() => {
                openPaymentDrawer();
                const select = document.querySelector('#paymentDrawer select[name="target_id"]');
                if (select) {
                    select.value = targetId;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }

                if (urlAmount) {
                    const amountInput = document.querySelector('#paymentDrawer input[name="amount"]');
                    if (amountInput) amountInput.value = urlAmount;
                }

                const typeSelect = document.getElementById('q-payment-type');
                if (typeSelect) {
                    if (urlType) {
                        typeSelect.value = urlType;
                    } else {
                        typeSelect.value = targetId.startsWith('jw_') ? 'JOB_WORK' : 'SALARY';
                    }
                    if (typeof toggleLoanFields === 'function') toggleLoanFields(typeSelect.value);
                }

                if (urlNotes) {
                    const notesInput = document.getElementById('q-payment-notes');
                    if (notesInput) notesInput.value = urlNotes;
                }
            }, 400);
        } else if (action === 'profile' && targetId) {
            setTimeout(() => {
                if (targetId.startsWith('jw_')) {
                    openJobWorkerProfile(targetId.replace('jw_', ''));
                } else if (targetId.startsWith('w_')) {
                    openWorkerProfile(targetId.replace('w_', ''));
                }
            }, 400);
        }
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', initLedgerTabAndAction);
    } else {
        initLedgerTabAndAction();
    }

;

    document.addEventListener("DOMContentLoaded", function() {
        const toasts = document.querySelectorAll('.toast');

        toasts.forEach(toast => {
            const close = toast.querySelector('.toast-close');
            const timeout = setTimeout(() => {
                toast.style.opacity = 0;
                setTimeout(() => toast.remove(), 300);
            }, 5000);

            close.addEventListener('click', () => {
                clearTimeout(timeout);
                toast.style.opacity = 0;
                setTimeout(() => toast.remove(), 300);
            });
        });

        // Mobile responsive sidebar toggle controls
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const sidebar = document.querySelector('.sidebar');

        function toggleSidebar() {
            sidebar.classList.toggle('active');
            sidebarOverlay.classList.toggle('active');
        }

        function closeSidebar() {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        }

        if (sidebarToggle && sidebar && sidebarOverlay) {
            sidebarToggle.addEventListener('click', toggleSidebar);
            sidebarOverlay.addEventListener('click', closeSidebar);

            // Dismiss drawer on escape keypress
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape') {
                    closeSidebar();
                }
            });

            // Dismiss drawer on navigation item clicks (useful for mobile SPAs or smooth links)
            const menuLinks = sidebar.querySelectorAll('.menu a');
            menuLinks.forEach(link => {
                link.addEventListener('click', closeSidebar);
            });
        }

        // Globally auto-select all content on focus for text and number inputs
        document.addEventListener('focusin', function(e) {
            if (e.target && e.target.tagName === 'INPUT') {
                const inputType = e.target.type;
                if (inputType === 'number' || inputType === 'text') {
                    setTimeout(() => {
                        if (typeof e.target.select === 'function') {
                            e.target.select();
                        }
                    }, 0);
                }
            }
        });

        // Register PWA Service Worker for Mobile Installation (iOS & Android)
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/static/sw.js').then(function(reg) {
                console.log('Foundry ERP PWA ServiceWorker registered:', reg.scope);
            }).catch(function(err) {
                console.log('PWA ServiceWorker registration failed:', err);
            });
        }
    });

;

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

;

    // Notification Drawer functions
    function openNotificationDrawer() {
        document.getElementById('notificationBackdrop').style.display = 'block';
        document.getElementById('notificationDrawer').style.right = '0';
        fetchNotifications();
    }

    function closeNotificationDrawer() {
        document.getElementById('notificationBackdrop').style.display = 'none';
        document.getElementById('notificationDrawer').style.right = '-650px';
    }

    function fetchNotifications() {
        fetch('/api/notifications/')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    updateNotificationBadges(data.notifications.length);
                    renderNotifications(data.notifications);
                }
            })
            .catch(err => console.error("Error fetching notifications:", err));
    }

    function updateNotificationBadges(count) {
        const badges = document.querySelectorAll('.notification-badge');
        badges.forEach(badge => {
            if (count > 0) {
                badge.innerText = count;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        });
    }

    function renderNotifications(notifs) {
        const listEl = document.getElementById('notificationList');
        if (!listEl) return;

        if (notifs.length === 0) {
            listEl.innerHTML = `
                <div style="text-align:center; padding:60px 20px; color:var(--text-secondary);">
                    <div style="font-size: 40px; margin-bottom: 16px;">✨</div>
                    <h4 style="margin:0 0 8px; font-weight:800; color:white;">All Clear!</h4>
                    <p style="margin:0; font-size:13px; opacity:0.7;">No active alerts or stock warnings at this time.</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = '';
        notifs.forEach(n => {
            let bg = 'rgba(255,255,255,0.02)';
            let border = 'rgba(255,255,255,0.06)';
            let accentColor = '#60a5fa'; // Blue info default
            let icon = 'ℹ️';

            if (n.type === 'WARNING') {
                bg = 'rgba(245, 158, 11, 0.03)';
                border = 'rgba(245, 158, 11, 0.12)';
                accentColor = '#f59e0b';
                icon = '⚠️';
            } else if (n.type === 'SUCCESS') {
                bg = 'rgba(16, 185, 129, 0.03)';
                border = 'rgba(16, 185, 129, 0.12)';
                accentColor = '#10b981';
                icon = '✅';
            } else if (n.type === 'ERROR') {
                bg = 'rgba(239, 68, 68, 0.03)';
                border = 'rgba(239, 68, 68, 0.12)';
                accentColor = '#ef4444';
                icon = '🚨';
            }

            const card = document.createElement('div');
            card.style.background = bg;
            card.style.border = `1px solid ${border}`;
            card.style.borderRadius = '16px';
            card.style.padding = '16px 20px';
            card.style.position = 'relative';
            card.style.display = 'flex';
            card.style.gap = '14px';
            card.style.transition = 'transform 0.2s';
            card.onmouseover = () => card.style.transform = 'translateY(-2px)';
            card.onmouseout = () => card.style.transform = 'translateY(0)';

            let contentHTML = `
                <div style="font-size: 20px; margin-top: 2px;">${icon}</div>
                <div style="flex:1; min-width:0;">
                    <div style="display:flex; justify-content:space-between; align-items:start; gap:10px;">
                        <h4 style="margin:0 0 6px; font-weight:800; color:white; font-size:15px;">${n.title}</h4>
                        <span style="font-size:11px; color:var(--text-secondary); white-space:nowrap;">${n.created_at}</span>
                    </div>
                    <p style="margin:0; font-size:13.5px; color:var(--text-secondary); line-height:1.45; word-wrap:break-word;">${n.message}</p>
            `;

            if (n.link) {
                contentHTML += `
                    <a href="${n.link}" style="display:inline-flex; align-items:center; gap:4px; font-size:12px; font-weight:bold; color:${accentColor}; text-decoration:none; margin-top:10px; text-transform:uppercase; letter-spacing:0.5px;">
                        Resolve Action &rarr;
                    </a>
                `;
            }

            contentHTML += `
                </div>
                <button onclick="dismissNotification(${n.id}, event)" style="background:none; border:none; color:var(--text-secondary); font-size:18px; cursor:pointer; padding:0 4px; align-self:start; line-height:1;" title="Dismiss">&times;</button>
            `;

            card.innerHTML = contentHTML;
            listEl.appendChild(card);
        });
    }

    function dismissNotification(id, event) {
        if (event) event.stopPropagation();
        
        const formData = new FormData();
        formData.append('id', id);
        formData.append('csrfmiddlewaretoken', 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW');

        fetch('/api/notifications/read/', {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                fetchNotifications();
            }
        })
        .catch(err => console.error("Error dismissing notification:", err));
    }

    function clearAllNotifications() {
        const formData = new FormData();
        formData.append('id', 'all');
        formData.append('csrfmiddlewaretoken', 'DfYSrr8jPPUeScXJ2Y8BVBJTJHGv0OPzAs3Y4QzmaNgEcNdLTiD5gCLgXPjVxYTW');

        fetch('/api/notifications/read/', {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                fetchNotifications();
            }
        })
        .catch(err => console.error("Error clearing notifications:", err));
    }

    // Auto-fetch notifications on load, and poll every 60 seconds
    document.addEventListener("DOMContentLoaded", function() {
        fetchNotifications();
        setInterval(fetchNotifications, 60000);

        // Mobile touch & click support for data-tooltip elements
        document.querySelectorAll("[data-tooltip]").forEach(el => {
            el.addEventListener("click", function(e) {
                if ('ontouchstart' in window || navigator.maxTouchPoints > 0) {
                    e.stopPropagation();
                    const isAlreadyActive = this.classList.contains("active-tooltip");
                    document.querySelectorAll(".active-tooltip").forEach(activeEl => activeEl.classList.remove("active-tooltip"));
                    if (!isAlreadyActive) {
                        this.classList.add("active-tooltip");
                    }
                }
            });
        });

        document.addEventListener("click", function() {
            document.querySelectorAll(".active-tooltip").forEach(el => el.classList.remove("active-tooltip"));
        });
    });

;

(function autoDetectExactHardware() {
    try {
        if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
            navigator.userAgentData.getHighEntropyValues(['model']).then(he => {
                if (he.model) {
                    fetch('/api/devices/update-hardware/', {
                        method: 'POST',
                        body: JSON.stringify({ exact_model: he.model }),
                        headers: { 'Content-Type': 'application/json' }
                    });
                }
            }).catch(() => {});
        }
    } catch(e) {}
})();
<!-- REAL-TIME PAGE HEARTBEAT TELEMETRY -->
<script>
(function startActivePageHeartbeat() {
    function sendHeartbeat() {
        if (document.visibilityState === 'visible') {
            const pagePath = window.location.pathname + window.location.search;
            fetch(`/api/heartbeat/?page_path=${encodeURIComponent(pagePath)}`).catch(() => {});
        }
    }
    sendHeartbeat();
    setInterval(sendHeartbeat, 10000);
})();
