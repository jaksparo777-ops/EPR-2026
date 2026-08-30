
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
        formData.append('csrfmiddlewaretoken', '"django_var"');

        try {
            const response = await fetch('/* dj */', {
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

    function openAttendanceDrawer() {
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
        loadAttendanceForDate();
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
                
                let btnClass = 'present';
                if (record.status === 'ABSENT') btnClass = 'absent';
                else if (record.status === 'HALF_DAY') btnClass = 'half';
                
                container.querySelector(`.toggle-btn.${btnClass}`).classList.add('active');
            } else {
                // Default to Present
                statusInput.value = 'PRESENT';
                otInput.value = 0;
                container.querySelector('.toggle-btn.present').classList.add('active');
            }
        });
    }

    const recipientLoanMap = {
        /* dj */
        "w_"django_var"": "django_var",
        /* dj */
        /* dj */
        "jw_"django_var"": "django_var",
        /* dj */
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

    function openPaymentDrawer() {
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
        updateRecipientLoanDeductionSection();
    }

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
        selectedMonth: '"django_var"'
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

        const initialMonth = '"django_var"';
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
                    if (mSub) mSub.textContent = `Clears "django_var" (₹${currentDuesData.monthlyDue})`;
                    
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
    let drawerCurrentMonth = '"django_var"';
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
        drawerCurrentMonth = '"django_var"';
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
                drawerMonthPicker.setDate('"django_var"', false);
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
                /* dj */
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
                /* dj */

                let checkboxTdHtml = '';
                /* dj */
                checkboxTdHtml = `
                    <td style="padding:10px; text-align:center;">
                        <input type="checkbox" class="tx-select-checkbox" data-tx-id="${entry.id}" data-entry-type="${entry.type === 'PAYMENT' ? 'PAYMENT' : 'TX'}" onchange="updateBulkDeleteTxButton()" style="width:16px; height:16px; accent-color:#ef4444; cursor:pointer;">
                    </td>
                `;
                /* dj */

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
        /* dj */
        <option value=""django_var"">"django_var"/* dj */ - "django_var"/* dj *//* dj */ ("django_var")/* dj */</option>
        /* dj */
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
            const res = await fetch('/* dj */', {
                method: 'POST',
                body: fd,
                headers: {'X-CSRFToken': '"django_var"'}
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
            headers: {'X-CSRFToken': '"django_var"'}
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
            
            await fetch('/* dj */', {
                method: 'POST',
                body: fd,
                headers: {'X-CSRFToken': '"django_var"'}
            });
        }
        location.reload();
    }

    async function savePayment() {
        const form = document.getElementById('paymentForm');
        const formData = new FormData(form);

        try {
            const response = await fetch('/* dj */', {
                method: 'POST',
                body: formData,
                headers: {'X-CSRFToken': '"django_var"'}
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
        
        const currentMonth = '"django_var"';
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
                        /* dj */
                        const pType = p.raw_type || p.type || 'ADVANCE';
                        const pMode = p.mode || 'CASH';
                        const pDate = p.raw_date || p.date;
                        actionsHtml = `
                            <td style="padding:6px 10px; text-align:right; white-space:nowrap;">
                                <button type="button" onclick="openEditPaymentModal(${p.id}, '${pDate}', ${p.amount}, '${pType}', '${pMode}')" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer; margin-right:4px;">✏️ EDIT</button>
                                <button type="button" onclick="deletePayment(${p.id}, ${p.amount})" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:3px 8px; font-size:10px; font-weight:800; border-radius:5px; cursor:pointer;">🗑️ DELETE</button>
                            </td>
                        `;
                        /* dj */
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
        
        fetch("/* dj */", {
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
        formData.append('csrfmiddlewaretoken', '"django_var"');

        fetch("/* dj */", {
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

