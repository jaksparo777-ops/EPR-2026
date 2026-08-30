
    document.addEventListener('DOMContentLoaded', function() {
        const btnStaff = document.getElementById('btn-staff');
        const btnJw = document.getElementById('btn-jw');
        const btnSheet = document.getElementById('btn-sheet');

        if (btnStaff) btnStaff.addEventListener('click', function(e) { if(e) e.preventDefault(); showSection('staff'); });
        if (btnJw) btnJw.addEventListener('click', function(e) { if(e) e.preventDefault(); showSection('jw'); });
        if (btnSheet) btnSheet.addEventListener('click', function(e) { if(e) e.preventDefault(); showSection('sheet'); });

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
