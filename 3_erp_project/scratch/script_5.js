
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
        /* dj */
        { id: ""django_var"", name: ""django_var"" },
        /* dj */
    ];

    const allJobWorkers = [
        /* dj */
        { id: ""django_var"", name: ""django_var"" },
        /* dj */
    ];

    async function compileBulkPDFs(items, isJobWorker) {
        const modal = document.getElementById('bulkDownloadModal');
        const progressText = document.getElementById('bulkProgressText');
        const progressBar = document.getElementById('bulkProgressBar');
        const currentMonth = ""django_var"";

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
        const currentMonth = ""django_var"";
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
            headers: {'X-CSRFToken': '"django_var"'}
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
            headers: {'X-CSRFToken': '"django_var"'}
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
                    'X-CSRFToken': '"django_var"'
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
            headers: {'X-CSRFToken': '"django_var"'}
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
