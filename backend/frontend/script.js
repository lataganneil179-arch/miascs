
/* ==========================================
   MIASCS - MONTALBAN INFIRMARY
   Frontend JavaScript
   FastAPI + Firebase Firestore Integration
========================================== */

// ==========================================
// 1. CONFIGURATION
// ==========================================

const API_URL = "http://127.0.0.1:8000";

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

let authToken = null;

// ==========================================
// 2. ICONS
// ==========================================

const IC = {
    home: '<path d="M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
    cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    chev: '<path d="M9 6l6 6-6 6"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>'
};

const icons = () => {
    $$('i[data-i]').forEach(e => {
        e.innerHTML = `<svg viewBox="0 0 24 24">${IC[e.dataset.i] || ''}</svg>`;
    });
};

// ==========================================
// 3. TOAST NOTIFICATION
// ==========================================

let tt;

const toast = message => {
    const t = $('#toast');
    t.textContent = message;
    t.classList.add('show');

    clearTimeout(tt);

    tt = setTimeout(() => {
        t.classList.remove('show');
    }, 2500);
};

// ==========================================
// 4. SCREEN NAVIGATION
// ==========================================

const S = [
    'login',
    'register',
    'home',
    'appointments',
    'profile',
    'admin'
];

const show = n => {
    if (!S.includes(n) || (n === 'admin' && !authToken)) n = 'login';

    S.forEach(s => {
        $('#' + s).hidden = s !== n;
    });

    $('#nav').hidden = !['home', 'appointments', 'profile'].includes(n);
    document.body.classList.toggle('admin-mode', n === 'admin');

    $$('#nav button').forEach(b => {
        b.classList.toggle('on', b.dataset.go === n);
    });

    scrollTo(0, 0);
};

const go = n => {
    location.hash = n;
};

addEventListener('hashchange', () => {
    show(location.hash.slice(1));
});

// ==========================================
// 5. APPOINTMENTS
// ==========================================

let appointments = [];
let tab = 'up';
let doctorsLoaded = false;
let adminUsers = [];
let adminAppointments = [];

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
}[character]));

const errorMessage = (result, fallback) => {
    if (typeof result.detail === 'string') return result.detail;
    if (Array.isArray(result.detail)) {
        return result.detail.map(item => item.msg).join(', ');
    }
    return fallback;
};

async function adminRequest(path, options = {}) {
    const headers = {
        'Accept': 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
        'Authorization': `Bearer ${authToken}`
    };
    const response = await fetch(`${API_URL}${path}`, { ...options, headers });
    const result = await response.json();

    if (!response.ok) {
        throw new Error(errorMessage(result, 'Admin request failed.'));
    }

    return result;
}

function showAdminMessage(message, isError = false) {
    const element = $('#adminMessage');
    element.textContent = message;
    element.classList.toggle('error', isError);
    element.hidden = !message;
}

function showAdminPanel(panel) {
    const panels = {
        overview: ['adminOverview', 'Overview'],
        appointments: ['adminAppointments', 'Appointments'],
        users: ['adminUsers', 'Patient accounts']
    };
    const selected = panels[panel] ? panel : 'overview';

    Object.entries(panels).forEach(([key, [id]]) => {
        $('#' + id).hidden = key !== selected;
    });
    $('#adminTitle').textContent = panels[selected][1];
    $$('#admin .admin-sidebar [data-admin-panel]').forEach(button => {
        button.classList.toggle('active', button.dataset.adminPanel === selected);
    });
}

function renderAdminAppointments() {
    const search = $('#appointmentSearch').value.trim().toLowerCase();
    const status = $('#appointmentStatusFilter').value;
    const filtered = adminAppointments.filter(appointment => {
        const matchesStatus = status === 'all' || appointment.status === status;
        const searchable = [
            appointment.patientName,
            appointment.patientCode,
            appointment.doctorName,
            appointment.department
        ].join(' ').toLowerCase();
        return matchesStatus && searchable.includes(search);
    });

    $('#adminAppointmentRows').innerHTML = filtered.length
        ? filtered.map(appointment => `
            <tr>
                <td><strong>${escapeHtml(appointment.patientName)}</strong><small>${escapeHtml(appointment.patientCode || appointment.patientId)}</small></td>
                <td>${escapeHtml(appointment.doctorName)}</td>
                <td>${escapeHtml(appointment.department)}</td>
                <td>${escapeHtml(appointment.date.slice(0, 10))}<small>${escapeHtml(appointment.time)}</small></td>
                <td><span class="admin-status ${escapeHtml(appointment.status)}">${escapeHtml(appointment.status)}</span></td>
                <td>${appointment.status === 'confirmed'
                    ? `<div class="admin-actions"><button class="danger" type="button" data-admin-cancel-appointment="${escapeHtml(appointment.id)}">Cancel</button></div>`
                    : '—'}</td>
            </tr>
        `).join('')
        : '<tr><td class="admin-empty" colspan="6">No matching appointments.</td></tr>';
}

function renderAdminUsers() {
    const search = $('#userSearch').value.trim().toLowerCase();
    const status = $('#userStatusFilter').value;
    const filtered = adminUsers.filter(user => {
        const matchesStatus = status === 'all'
            || (status === 'active' ? user.isActive : !user.isActive);
        const searchable = [
            user.name,
            user.username,
            user.email,
            user.patientCode
        ].join(' ').toLowerCase();
        return matchesStatus && searchable.includes(search);
    });

    $('#adminUserRows').innerHTML = filtered.length
        ? filtered.map(user => `
            <tr>
                <td><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.email)}</small></td>
                <td>${escapeHtml(user.username)}</td>
                <td>${escapeHtml(user.phone || '—')}</td>
                <td>${escapeHtml(user.patientCode || '—')}</td>
                <td><span class="admin-status ${user.isActive ? '' : 'inactive'}">${user.isActive ? 'Active' : 'Deactivated'}</span></td>
                <td><div class="admin-actions">
                    <button type="button" data-admin-user-toggle="${escapeHtml(user.id)}">${user.isActive ? 'Deactivate' : 'Reactivate'}</button>
                    <button class="danger" type="button" data-admin-user-delete="${escapeHtml(user.id)}">Delete</button>
                </div></td>
            </tr>
        `).join('')
        : '<tr><td class="admin-empty" colspan="6">No matching patient accounts.</td></tr>';
}

function renderAdminDashboard() {
    const confirmedCount = adminAppointments.filter(item => item.status === 'confirmed').length;
    const inactiveCount = adminUsers.filter(user => !user.isActive).length;

    $('#adminAppointmentCount').textContent = adminAppointments.length;
    $('#adminUpcomingCount').textContent = confirmedCount;
    $('#adminPatientCount').textContent = adminUsers.length;
    $('#adminInactiveCount').textContent = inactiveCount;

    const recent = [...adminAppointments]
        .sort((left, right) =>
            `${right.date}${right.time}`.localeCompare(`${left.date}${left.time}`)
        )
        .slice(0, 5);
    $('#adminRecentRows').innerHTML = recent.length
        ? recent.map(appointment => `
            <tr>
                <td><strong>${escapeHtml(appointment.patientName)}</strong><small>${escapeHtml(appointment.patientCode || appointment.patientId)}</small></td>
                <td>${escapeHtml(appointment.doctorName)}</td>
                <td>${escapeHtml(appointment.department)}</td>
                <td>${escapeHtml(appointment.date.slice(0, 10))}</td>
                <td><span class="admin-status ${escapeHtml(appointment.status)}">${escapeHtml(appointment.status)}</span></td>
            </tr>
        `).join('')
        : '<tr><td class="admin-empty" colspan="5">No bookings yet.</td></tr>';

    renderAdminAppointments();
    renderAdminUsers();
}

async function loadAdminDashboard() {
    showAdminMessage('Loading dashboard data…');
    const [appointmentsResult, usersResult] = await Promise.all([
        adminRequest('/api/admin/appointments'),
        adminRequest('/api/admin/users')
    ]);
    adminAppointments = appointmentsResult;
    adminUsers = usersResult;
    renderAdminDashboard();
    showAdminMessage('');
}

// ==========================================
// 6. RENDER APPOINTMENTS
// ==========================================

function renderList() {
    const statuses = {
        up: ['confirmed'],
        past: ['completed'],
        cx: ['cancelled']
    };
    const L = appointments.filter(appointment =>
        statuses[tab].includes(appointment.status)
    );

    const T = {
        up: 'Your upcoming visits',
        past: 'Your past visits',
        cx: 'Your canceled visits'
    };

    $('#ctitle').textContent = T[tab];

    $('#ccount').textContent =
        L.length + (L.length === 1
            ? ' appointment'
            : ' appointments');

    $('#list').innerHTML = L.length
        ? L.map(a => `
            <button class="ap" data-appointment-id="${escapeHtml(a.id)}">
                <div class="t">
                    <div class="av">${escapeHtml(a.doctorName.slice(0, 2).toUpperCase())}</div>
                    <div>
                        <b>${escapeHtml(a.doctorName)}</b>
                        <small>${escapeHtml(a.department)}</small>
                    </div>
                    <i data-i="chev"></i>
                </div>

                <div class="bt">
                    <span>${escapeHtml(a.date.slice(0, 10))} · ${escapeHtml(a.time)}</span>
                    <span class="st ${tab === 'cx' ? 'x' : ''}">
                        ${tab === 'cx' ? 'Canceled' : tab === 'past' ? 'Completed' : 'Confirmed'}
                    </span>
                </div>
            </button>
        `).join('')
        : '<p class="empty">No appointments here yet.</p>';

    icons();
    renderNext();
}

async function loadAppointments() {
    const response = await fetch(`${API_URL}/api/appointments`, {
        headers: {
            'Authorization': `Bearer ${authToken}`,
            'Accept': 'application/json'
        }
    });
    const result = await response.json();

    if (!response.ok) {
        throw new Error(errorMessage(result, 'Unable to load appointments.'));
    }

    appointments = result;
    renderList();
}

// ==========================================
// 7. NEXT APPOINTMENT
// ==========================================

function renderNext() {
    const a = appointments
        .filter(appointment => appointment.status === 'confirmed')
        .sort((left, right) =>
            `${left.date}${left.time}`.localeCompare(`${right.date}${right.time}`)
        )[0];

    $('#next').innerHTML = a
        ? `
            <div class="ch">
                <div class="ic"><i data-i="cal"></i></div>
                <div>
                    <h3>Next Appointment</h3>
                    <small>Your upcoming visit</small>
                </div>
                <span class="badge">Confirmed</span>
            </div>

            <div class="date">
                <div>
                    <b>${escapeHtml(a.date.slice(0, 10))}</b>
                    <span>${escapeHtml(a.time)}</span>
                </div>
            </div>

            <div class="row2">
                <span>Department<b>${escapeHtml(a.department)}</b></span>
                <span style="text-align:right">
                    Doctor<b>${escapeHtml(a.doctorName)}</b>
                </span>
            </div>

            <div class="acts">
                <button data-t="Pick a new date and time for this visit">
                    Reschedule
                </button>
                <button class="cx" data-cancel-id="${escapeHtml(a.id)}">Cancel</button>
            </div>
        `
        : `
            <div class="ch">
                <div class="ic"><i data-i="cal"></i></div>
                <div>
                    <h3>Next Appointment</h3>
                    <small>No upcoming appointments</small>
                </div>
            </div>
            <p class="empty">You have no appointments yet. Book one when you're ready.</p>
            <button class="btn" type="button" data-book>Book an appointment</button>
        `;

    const queueAppointment = a && a.queueNumber
        ? `<p class="empty">Your appointment ticket is <b>#${escapeHtml(a.queueNumber)}</b>.</p>`
        : '<p class="empty">Your queue number will appear here after you book an appointment.</p>';
    $('#queueStatus').innerHTML = `
        <div class="ch">
            <div class="ic"><i data-i="cal"></i></div>
            <div><h3>Queue Status</h3><small>${a ? escapeHtml(a.department) : 'No appointment yet'}</small></div>
        </div>
        ${queueAppointment}
    `;

    icons();
}

async function openBookingForm() {
    const form = $('#bookingForm');
    form.hidden = false;

    const date = new Date();
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    $('#bookDate').min = date.toISOString().slice(0, 10);

    if (doctorsLoaded) return;

    const response = await fetch(`${API_URL}/api/departments`, {
        headers: { 'Accept': 'application/json' }
    });
    const departments = await response.json();

    if (!response.ok) {
        throw new Error(errorMessage(departments, 'Unable to load doctors.'));
    }

    const doctorSelect = $('#bookDoctor');
    departments.forEach(department => {
        (department.doctors || []).forEach(doctor => {
            doctorSelect.add(new Option(
                `${doctor.name} - ${department.name}`,
                doctor.id
            ));
        });
    });
    doctorsLoaded = true;

    if (!doctorSelect.options.length || doctorSelect.options.length === 1) {
        toast('No doctors are available for booking right now.');
    }
}

$('#bookingForm').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;

    try {
        const response = await fetch(`${API_URL}/api/appointments`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                doctor_id: $('#bookDoctor').value,
                date: $('#bookDate').value,
                time: $('#bookTime').value
            })
        });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(errorMessage(result, 'Unable to book appointment.'));
        }

        appointments.push(result);
        form.reset();
        form.hidden = true;
        tab = 'up';
        $$('#tabs button').forEach(button => {
            button.classList.toggle('on', button.dataset.k === tab);
        });
        renderList();
        toast('Appointment booked successfully.');
    } catch (error) {
        console.error('Appointment booking error:', error);
        toast(error.message || 'Unable to book appointment.');
    } finally {
        submitButton.disabled = false;
    }
});

$('#cancelBooking').addEventListener('click', () => {
    $('#bookingForm').hidden = true;
});

async function cancelAppointment(appointmentId) {
    const response = await fetch(
        `${API_URL}/api/appointments/${encodeURIComponent(appointmentId)}/cancel`,
        {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Accept': 'application/json'
            }
        }
    );
    const result = await response.json();

    if (!response.ok) {
        throw new Error(errorMessage(result, 'Unable to cancel appointment.'));
    }

    appointments = appointments.map(appointment =>
        appointment.id === appointmentId ? result : appointment
    );
    renderList();
    toast('Appointment canceled.');
}

// ==========================================
// 8. GENERAL CLICK EVENTS
// ==========================================

document.addEventListener('click', e => {

    const adminPanel = e.target.closest('[data-admin-panel]');
    if (adminPanel) {
        showAdminPanel(adminPanel.dataset.adminPanel);
        return;
    }

    const toggleUser = e.target.closest('[data-admin-user-toggle]');
    if (toggleUser) {
        const user = adminUsers.find(item => item.id === toggleUser.dataset.adminUserToggle);
        if (!user || (user.isActive && !confirm(`Deactivate ${user.username || user.name}'s account?`))) {
            return;
        }
        adminRequest(`/api/admin/users/${encodeURIComponent(user.id)}`, {
            method: 'PATCH',
            body: JSON.stringify({ isActive: !user.isActive })
        }).then(updated => {
            adminUsers = adminUsers.map(item => item.id === updated.id ? updated : item);
            renderAdminDashboard();
            toast(updated.isActive ? 'Account reactivated.' : 'Account deactivated.');
        }).catch(error => {
            console.error('Account status update error:', error);
            showAdminMessage(error.message || 'Unable to update account status.', true);
        });
        return;
    }

    const deleteUser = e.target.closest('[data-admin-user-delete]');
    if (deleteUser) {
        const user = adminUsers.find(item => item.id === deleteUser.dataset.adminUserDelete);
        if (!user || !confirm(
            `Permanently delete ${user.username || user.name} and all of their appointment records? This cannot be undone.`
        )) {
            return;
        }
        adminRequest(`/api/admin/users/${encodeURIComponent(user.id)}`, {
            method: 'DELETE'
        }).then(() => {
            adminUsers = adminUsers.filter(item => item.id !== user.id);
            adminAppointments = adminAppointments.filter(item => item.patientId !== user.id);
            renderAdminDashboard();
            toast('Account and appointment records deleted.');
        }).catch(error => {
            console.error('Account deletion error:', error);
            showAdminMessage(error.message || 'Unable to delete account.', true);
        });
        return;
    }

    const cancelAppointmentButton = e.target.closest('[data-admin-cancel-appointment]');
    if (cancelAppointmentButton) {
        const appointmentId = cancelAppointmentButton.dataset.adminCancelAppointment;
        if (!confirm('Cancel this appointment?')) return;
        adminRequest(`/api/appointments/${encodeURIComponent(appointmentId)}/cancel`, {
            method: 'POST'
        }).then(updated => {
            adminAppointments = adminAppointments.map(item =>
                item.id === updated.id ? { ...item, status: updated.status } : item
            );
            renderAdminDashboard();
            toast('Appointment canceled.');
        }).catch(error => {
            console.error('Appointment cancellation error:', error);
            showAdminMessage(error.message || 'Unable to cancel appointment.', true);
        });
        return;
    }

    const book = e.target.closest('[data-book]');

    if (book) {
        e.preventDefault();
        go('appointments');
        openBookingForm().catch(error => {
            console.error('Doctor loading error:', error);
            toast(error.message || 'Unable to load doctors.');
        });
        return;
    }

    const t = e.target.closest('[data-t]');

    if (t) {
        e.preventDefault();
        toast(t.dataset.t);
    }

    const g = e.target.closest('[data-go]');

    if (g) {
        go(g.dataset.go);
    }

    const c = e.target.closest('[data-cancel-id]');

    if (c) {
        cancelAppointment(c.dataset.cancelId).catch(error => {
            console.error('Appointment cancellation error:', error);
            toast(error.message || 'Unable to cancel appointment.');
        });
        return;
    }

    const ap = e.target.closest('.ap');

    if (ap) {
        toast('Queue number and visit details open here');
    }
});

$('#adminRefresh').addEventListener('click', () => {
    loadAdminDashboard().catch(error => {
        console.error('Admin dashboard refresh error:', error);
        showAdminMessage(error.message || 'Unable to refresh dashboard.', true);
    });
});

$('#appointmentSearch').addEventListener('input', renderAdminAppointments);
$('#appointmentStatusFilter').addEventListener('change', renderAdminAppointments);
$('#userSearch').addEventListener('input', renderAdminUsers);
$('#userStatusFilter').addEventListener('change', renderAdminUsers);

$('#adminLogout').addEventListener('click', () => {
    authToken = null;
    adminUsers = [];
    adminAppointments = [];
    showAdminMessage('');
    $('#pw').value = '';
    $$('#role button').forEach((button, index) => {
        button.classList.toggle('on', index === 0);
    });
    go('login');
    toast('You have been logged out.');
});

// ==========================================
// 9. APPOINTMENT TABS
// ==========================================

$('#tabs').addEventListener('click', e => {
    const b = e.target.closest('button');

    if (!b) return;

    tab = b.dataset.k;

    $$('#tabs button').forEach(x => {
        x.classList.toggle('on', x === b);
    });

    renderList();
});

// ==========================================
// 10. PATIENT / ADMIN ROLE SELECTOR
// ==========================================

$('#role').addEventListener('click', e => {
    const b = e.target.closest('button');

    if (!b) return;

    $$('#role button').forEach(x => {
        x.classList.toggle('on', x === b);
    });
});

// ==========================================
// 11. SHOW / HIDE PASSWORD
// ==========================================

$('#show').onclick = () => {
    const p = $('#pw');

    const h = p.type === 'password';

    p.type = h ? 'text' : 'password';

    $('#show').textContent = h ? 'Hide' : 'Show';
};

// ==========================================
// 12. PATIENT REGISTRATION - FIREBASE
// ==========================================

$('#registerForm').addEventListener('submit', async e => {

    e.preventDefault();

    const form = e.currentTarget;

    const password = $('#regPassword').value;
    const confirm = $('#regConfirm').value;

    // Validate form
    if (!form.reportValidity()) return;

    // Check password confirmation
    if (password !== confirm) {

        $('#regConfirm').setCustomValidity(
            'Passwords do not match.'
        );

        $('#regConfirm').reportValidity();

        return;
    }

    $('#regConfirm').setCustomValidity('');

    // Collect patient information
    const patientData = {
        name: $('#regName').value.trim(),
        email: $('#regEmail').value.trim(),
        username: $('#regUser').value.trim(),
        phone: $('#regPhone').value.trim(),
        password: password
    };

    const submitButton = form.querySelector(
        'button[type="submit"]'
    );

    submitButton.disabled = true;
    submitButton.textContent = 'Creating Account...';

    try {

        const response = await fetch(
            `${API_URL}/api/auth/register`,
            {
                method: 'POST',

                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },

                body: JSON.stringify(patientData)
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail || 'Registration failed.'
            );
        }

        // Successful registration
        toast('Account created successfully!');

        // Automatically fill login username
        $('#u').value = patientData.username;

        // Clear registration fields
        form.reset();

        // Return to login
        setTimeout(() => {
            go('login');
        }, 1200);

    } catch (error) {

        console.error('Registration error:', error);

        toast(error.message || 'Unable to connect to server.');

    } finally {

        submitButton.disabled = false;

        submitButton.textContent = 'Create Patient Account';
    }
});

// Clear password validation
$('#regConfirm').addEventListener('input', () => {
    $('#regConfirm').setCustomValidity('');
});

// ==========================================
// 13. PATIENT LOGIN
// ==========================================

$('#loginBtn').onclick = async () => {

    const identifier = $('#u').value.trim();
    const password = $('#pw').value;
    const role = $('#role button.on').textContent.trim().toLowerCase();

    if (!identifier || !password) {
        toast('Please enter your username and password.');
        return;
    }

    const loginButton = $('#loginBtn');

    loginButton.disabled = true;
    loginButton.textContent = 'Logging in...';

    try {

        const response = await fetch(
            `${API_URL}/api/auth/login`,
            {
                method: 'POST',

                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },

                body: JSON.stringify({ identifier, password, role })
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail || 'Invalid login credentials.'
            );
        }

        authToken = result.token;
        if (result.role === 'administrator') {
            adminUsers = [];
            adminAppointments = [];
            showAdminPanel('overview');
            go('admin');
            toast('Administrator login successful.');
            try {
                await loadAdminDashboard();
            } catch (error) {
                console.error('Admin dashboard loading error:', error);
                showAdminMessage(error.message || 'Unable to load admin dashboard.', true);
            }
            return;
        }

        appointments = [];
        renderList();
        const patient = result.patient;
        const username = patient.username || identifier;

        $('#homeGreeting').textContent = `Welcome, ${username}`;
        $('#profileUsername').textContent = username;
        $('#patientCode').textContent = `Patient ID: ${patient.patientCode}`;
        $$('[data-account-initials]').forEach(element => {
            element.textContent = username.slice(0, 2).toUpperCase();
        });

        // Open patient dashboard
        go('home');

        toast('Login successful!');
        try {
            await loadAppointments();
        } catch (error) {
            console.error('Appointment loading error:', error);
            toast(error.message || 'Unable to load appointments.');
        }

    } catch (error) {

        console.error('Login error:', error);

        toast(error.message || 'Unable to log in.');

    } finally {

        loginButton.disabled = false;
        loginButton.textContent = 'Login';
    }
};

// ==========================================
// 14. LOGOUT
// ==========================================

$('#logout').onclick = () => {

    authToken = null;
    appointments = [];
    renderList();
    $('#bookingForm').hidden = true;

    $('#pw').value = '';

    go('login');

    toast('You have been logged out.');
};

// ==========================================
// 15. APPOINTMENT REMINDERS
// ==========================================

$('#rem').onclick = e => {

    const on =
        e.currentTarget.getAttribute('aria-checked') !== 'true';

    e.currentTarget.setAttribute('aria-checked', on);

    toast(
        on
            ? 'Reminders turned on'
            : 'Reminders turned off'
    );
};

// ==========================================
// 16. INITIALIZE APPLICATION
// ==========================================

icons();

renderList();

show(location.hash.slice(1) || 'login');
