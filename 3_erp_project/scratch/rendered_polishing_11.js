
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
        formData.append('csrfmiddlewaretoken', 'cM3MBkhVpPE8RPcWoM0iN04u7UWAUe8jqEQpg2nAjtNZo1lnduVEO1RLGGcsFEbh');

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
        formData.append('csrfmiddlewaretoken', 'cM3MBkhVpPE8RPcWoM0iN04u7UWAUe8jqEQpg2nAjtNZo1lnduVEO1RLGGcsFEbh');

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
    });
