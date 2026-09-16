
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
        if (!val) return;
        let monthStr = val;
        if (typeof val === 'string' && val.length >= 7) {
            monthStr = val.substring(0, 7);
        }
        const currentTab = new URLSearchParams(window.location.search).get('tab') || 'staff';
        window.location.href = `/ledger/?tab=${currentTab}&month=${monthStr}`;
    }
    window.changeLedgerMonth = changeLedgerMonth;

    let hoveredCell = null;
    let currentModalCell = null;
    let currentSelectedStatus = 'PRESENT';
    const cellClickTimers = {};
    const cellClickCounts = {};

    // Track active hovered cell for keyboard hotkeys
    function setHoveredCell(cell) {
        hoveredCell = cell;
    }
    window.setHoveredCell = setHoveredCell;

    function clearHoveredCell(cell) {
        if (hoveredCell === cell) {
            hoveredCell = null;
        }
    }
    window.clearHoveredCell = clearHoveredCell;

    // Track mouseover globally as an extra safeguard
    document.addEventListener('mouseover', function(e) {
        const cell = e.target.closest('.attendance-cell');
        if (cell) {
            hoveredCell = cell;
        }
    });

    // Fast Mouse Multi-Click Handler: 1 Click = Present/Cycle, 2 Clicks = Absent, 3 Clicks = Half Day
    function handleAttendanceCellClick(cell, event) {
        if (event) {
            event.stopPropagation();
            event.preventDefault();
        }
        const cellKey = cell.getAttribute('data-worker-id') + '_' + cell.getAttribute('data-date');
        cellClickCounts[cellKey] = (cellClickCounts[cellKey] || 0) + 1;
        
        if (cellClickTimers[cellKey]) {
            clearTimeout(cellClickTimers[cellKey]);
        }

        cellClickTimers[cellKey] = setTimeout(async () => {
            const clicks = cellClickCounts[cellKey] || 1;
            cellClickCounts[cellKey] = 0;
            delete cellClickTimers[cellKey];

            const workerId = cell.getAttribute('data-worker-id');
            const date = cell.getAttribute('data-date');
            const currentStatus = cell.getAttribute('data-status') || 'NONE';
            const ot = cell.getAttribute('data-ot') || '0';

            let newStatus = 'PRESENT';
            if (clicks === 1) {
                // 1 Click: Cycle states (None/Other -> Present -> Half Day -> Absent -> None)
                if (currentStatus === 'NONE' || !currentStatus) newStatus = 'PRESENT';
                else if (currentStatus === 'PRESENT') newStatus = 'HALF_DAY';
                else if (currentStatus === 'HALF_DAY') newStatus = 'ABSENT';
                else if (currentStatus === 'ABSENT') newStatus = 'NONE';
                else newStatus = 'PRESENT';
            } else if (clicks === 2) {
                // 2 Clicks: Directly set Absent
                newStatus = 'ABSENT';
            } else if (clicks >= 3) {
                // 3 Clicks: Directly set Half Day
                newStatus = 'HALF_DAY';
            }

            // Optimistic in-place update
            updateCellUI(cell, newStatus, ot);
            cell.classList.remove('success-pulse', 'error-pulse');
            const updated = await saveAttendanceState(workerId, newStatus, date, ot);
            if (updated) {
                cell.classList.add('success-pulse');
            } else {
                cell.classList.add('error-pulse');
            }
        }, 260);
    }
    window.handleAttendanceCellClick = handleAttendanceCellClick;

    // Right-Click Context Menu: Open Overtime & Details Modal
    function handleAttendanceContextMenu(cell, event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        openAttendanceCellModal(cell, event);
        return false;
    }
    window.handleAttendanceContextMenu = handleAttendanceContextMenu;

    // Open Attendance Cell Modal on Right Click / Hotkey / Button
    function openAttendanceCellModal(cell, event) {
        if (event) {
            event.stopPropagation();
            event.preventDefault();
        }
        currentModalCell = cell;
        const workerId = cell.getAttribute('data-worker-id');
        const workerName = cell.getAttribute('data-worker-name') || 'Staff Member';
        const date = cell.getAttribute('data-date');
        const day = cell.getAttribute('data-day');
        const status = cell.getAttribute('data-status') || 'NONE';
        const ot = parseFloat(cell.getAttribute('data-ot') || '0');

        const nameEl = document.getElementById('attModalWorkerName');
        const dateEl = document.getElementById('attModalDateText');
        const otEl = document.getElementById('attModalOtInput');
        const backdrop = document.getElementById('attendanceCellModalBackdrop');
        const modal = document.getElementById('attendanceCellModal');

        if (nameEl) nameEl.textContent = workerName;
        if (dateEl) dateEl.textContent = `Date: Day ${day} (${date})`;
        if (otEl) otEl.value = ot > 0 ? ot : '0';

        currentSelectedStatus = (status === 'NONE' || !status) ? 'PRESENT' : status;
        highlightModalStatusButton(currentSelectedStatus);

        if (backdrop) {
            backdrop.style.setProperty('display', 'block', 'important');
        }
        if (modal) {
            modal.style.setProperty('display', 'block', 'important');
        }
    }
    window.openAttendanceCellModal = openAttendanceCellModal;

    function closeAttendanceCellModal() {
        const backdrop = document.getElementById('attendanceCellModalBackdrop');
        const modal = document.getElementById('attendanceCellModal');
        if (backdrop) backdrop.style.display = 'none';
        if (modal) modal.style.display = 'none';
        currentModalCell = null;
    }
    window.closeAttendanceCellModal = closeAttendanceCellModal;

    function highlightModalStatusButton(status) {
        document.querySelectorAll('.att-status-btn').forEach(btn => {
            if (btn.getAttribute('data-status') === status) {
                btn.style.boxShadow = '0 0 0 2px #60a5fa, inset 0 0 8px rgba(96,165,250,0.3)';
                btn.style.transform = 'scale(1.02)';
            } else {
                btn.style.boxShadow = 'none';
                btn.style.transform = 'none';
            }
        });
    }
    window.highlightModalStatusButton = highlightModalStatusButton;

    function setAttendanceModalStatus(status) {
        currentSelectedStatus = status;
        highlightModalStatusButton(status);
        // Instant save on status button click
        saveAttendanceModalData();
    }
    window.setAttendanceModalStatus = setAttendanceModalStatus;

    function adjustModalOt(addHours) {
        const input = document.getElementById('attModalOtInput');
        if (!input) return;
        const current = parseFloat(input.value || '0');
        input.value = Math.max(0, current + addHours);
    }
    window.adjustModalOt = adjustModalOt;

    async function saveAttendanceModalData() {
        if (!currentModalCell) return;
        const cell = currentModalCell;
        const workerId = cell.getAttribute('data-worker-id');
        const date = cell.getAttribute('data-date');
        const otInput = document.getElementById('attModalOtInput');
        const ot = parseFloat(otInput ? otInput.value : '0') || 0;
        const status = currentSelectedStatus;

        closeAttendanceCellModal();

        updateCellUI(cell, status, ot);
        cell.classList.remove('success-pulse', 'error-pulse');
        const updated = await saveAttendanceState(workerId, status, date, ot);
        if (updated) {
            cell.classList.add('success-pulse');
        } else {
            cell.classList.add('error-pulse');
            alert('Failed to save attendance for ' + date);
        }
    }
    window.saveAttendanceModalData = saveAttendanceModalData;

    // Keyboard Hotkey Listener (Hover over cell and press P/A/H/Y/C/1-9)
    document.addEventListener('keydown', async function(event) {
        // If typing in an input or modal is open, ignore global hotkeys
        if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA' || document.activeElement.tagName === 'SELECT')) {
            return;
        }

        const cell = hoveredCell || document.querySelector('.attendance-cell:hover');
        if (!cell) return;

        const key = event.key.toLowerCase();

        if (key === 'o' || key === 'enter' || key === ' ') {
            event.preventDefault();
            openAttendanceCellModal(cell, event);
            return;
        }

        let newStatus = null;
        let setOt = null;

        if (key === 'p') newStatus = 'PRESENT';
        else if (key === 'a') newStatus = 'ABSENT';
        else if (key === 'h') newStatus = 'HALF_DAY';
        else if (key === 'y') newStatus = 'HOLIDAY';
        else if (key === 'c' || key === '0' || event.key === 'Backspace' || event.key === 'Delete') {
            newStatus = 'NONE';
            setOt = 0;
        }
        else if (['1','2','3','4','5','6','7','8','9'].includes(key)) {
            setOt = parseFloat(key);
            const curStatus = cell.getAttribute('data-status');
            newStatus = (curStatus && curStatus !== 'NONE') ? curStatus : 'PRESENT';
        }

        if (newStatus !== null || setOt !== null) {
            event.preventDefault();
            const workerId = cell.getAttribute('data-worker-id');
            const date = cell.getAttribute('data-date');
            const finalStatus = newStatus !== null ? newStatus : (cell.getAttribute('data-status') || 'PRESENT');
            const finalOt = setOt !== null ? setOt : (cell.getAttribute('data-ot') || '0');

            updateCellUI(cell, finalStatus, finalOt);
            cell.classList.remove('success-pulse', 'error-pulse');
            try {
                const updated = await saveAttendanceState(workerId, finalStatus, date, finalOt);
                if (updated) {
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

    // AJAX helper to submit attendance state changes
    async function saveAttendanceState(workerId, status, date, otHours) {
        const formData = new FormData();
        formData.append('worker_id', workerId);
        formData.append('status', status);
        formData.append('date', date);
        formData.append('ot_hours', otHours);
        formData.append('csrfmiddlewaretoken', 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG');

        try {
            const response = await fetch('/api/attendance/mark/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'
                },
                body: formData
            });
            const data = await response.json();
            return data.status === 'success';
        } catch (err) {
            console.error(err);
            return false;
        }
    }
    window.saveAttendanceState = saveAttendanceState;

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
        if (indicator) {
            if (parsedOt > 0 && (status === 'PRESENT' || status === 'HALF_DAY')) {
                indicator.style.display = 'block';
                indicator.setAttribute('title', `OT: ${parsedOt}h`);
            } else {
                indicator.style.display = 'none';
            }
        }
    }
    window.updateCellUI = updateCellUI;

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
                if (statusInput) statusInput.value = record.status;
                if (otInput) otInput.value = record.ot;
                let btnClass = 'present';
                if (record.status === 'ABSENT') btnClass = 'absent';
                else if (record.status === 'HALF_DAY') btnClass = 'half';
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
        closeAllDrawers();
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
            d.style.setProperty('display', 'none', 'important');
            d.classList.remove('active');
        });
        if (typeof currentProfileWorkerId !== 'undefined') currentProfileWorkerId = null;
    }
    window.closeAllDrawers = closeAllDrawers;

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

    function onSettlementMonthChange(monthVal) {
        document.getElementById('q-settlement-period').value = monthVal;
        currentDuesData.selectedMonth = monthVal;
        
        fetch(`/api/labor/get-recipient-dues/?target_id=${encodeURIComponent(currentDuesData.targetId)}&month=${monthVal}`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    currentDuesData.monthlyDue = data.monthly_due;
                    const sel = document.getElementById('scope-target-month');
                    const selText = (sel && sel.selectedIndex >= 0 && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text.split('(')[0].trim() : monthVal;
                    
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

        updateRecipientLoanDeductionSection();
    }
    window.openQuickSettlementModal = openQuickSettlementModal;

    // JOB WORKER PROFILE LOGIC
    let currentProfileWorkerId = null;
    let drawerCurrentMode = 'monthly';
    function viewSettledVoucher(workerId, name, amount, monthName) {
        alert("📜 SETTLEMENT VOUCHER ARCHIVE\n-----------------------------------\nWorker / Unit: " + name + "\nMonth: " + monthName + "\nSettlement Amount Cleared: ₹" + amount + "\nStatus: CLOSED & ARCHIVED (Clean Slate Reset Active)\n-----------------------------------\nAll accounts for this cycle have been 100% settled.");
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
                headers: {'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'}
            });
        }
        location.reload();
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
    window.savePayment = savePayment;

    function quickLoanRepayment(workerId, emiAmount) {
        if (!confirm(`Record EMI payment of ₹${emiAmount}?`)) return;
        
        const formData = new FormData();
        formData.append('target_id', 'w_' + workerId);
        formData.append('amount', emiAmount);
        formData.append('payment_type', 'LOAN_REPAYMENT');
        formData.append('payment_mode', 'CASH');
        formData.append('notes', 'Monthly EMI repayment (Quick)');
        formData.append('csrfmiddlewaretoken', 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG');

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
        closeAllDrawers();
    }
    window.closeWorkerProfile = closeWorkerProfile;

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
    window.showWorkerTab = showWorkerTab;

