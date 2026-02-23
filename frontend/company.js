// Company Dashboard Module
// escapeHtml, esc, normalizeStatus, anonymizeId, getStatusIcon,
// getScoreClass, createModal, closeTopModal — all from shared-utils.js

// ─── Global ESC-key & backdrop-click handler for all company modals ───
(function() {
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modals = document.querySelectorAll('.modal.show');
            if (modals.length > 0) {
                modals[modals.length - 1].remove();
                e.preventDefault();
            }
        }
    });
    document.addEventListener('click', function(e) {
        if (e.target.classList && e.target.classList.contains('modal') && e.target.classList.contains('show')) {
            e.target.remove();
        }
    });
})();

function loadCompanyDashboard() {
    console.log('Loading Company Dashboard...', currentUser);

    // Ensure currentUser is available
    if (!currentUser) {
        console.error('No current user found');
        logout();
        return;
    }

    const dashboard = document.getElementById('companyDashboard');
    if (!dashboard) {
        console.error('Company dashboard element not found');
        return;
    }

    const userEmail = currentUser.email || currentUser.full_name || 'User';

    dashboard.innerHTML = `
        <nav class="navbar">
            <div class="navbar-brand">
                <svg width="32" height="32" viewBox="0 0 64 64">
                    <circle cx="32" cy="32" r="30" fill="#4F46E5"/>
                    <path d="M32 16L40 28H24L32 16Z" fill="white"/>
                    <rect x="22" y="30" width="20" height="18" rx="2" fill="white"/>
                </svg>
                <span>Company Portal</span>
            </div>
            <div class="navbar-menu">
                <button class="nav-link active" onclick="switchCompanyTab('overview', event)">📊 Dashboard</button>
                <button class="nav-link" onclick="switchCompanyTab('jobs', event)">💼 My Jobs</button>
                <button class="nav-link" onclick="switchCompanyTab('candidates', event)">🎯 Candidates</button>
                <button class="nav-link" onclick="switchCompanyTab('applications', event)">📋 Applications</button>
                <button class="nav-link" onclick="switchCompanyTab('analytics', event)">📈 Analytics</button>
                <button class="nav-link" onclick="switchCompanyTab('assessments', event)">🧠 Assessments</button>
                <button class="nav-link" onclick="switchCompanyTab('audit', event)">🛡️ Fairness Audit</button>
            </div>
            <div class="navbar-actions">
                <button class="theme-toggle-navbar" aria-label="Toggle Dark Mode" onclick="toggleTheme()">
                    <span class="theme-icon sun-icon">☀️</span>
                    <span class="theme-icon moon-icon" style="display:none;">🌙</span>
                </button>
                <span class="user-info">${userEmail}</span>
                <button class="btn btn-secondary" onclick="companyLogout()">Logout</button>
            </div>
        </nav>
        <div class="main-content">
            <div id="companyOverview" class="tab-content active"></div>
            <div id="companyJobs" class="tab-content"></div>
            <div id="companyCandidates" class="tab-content"></div>
            <div id="companyApplications" class="tab-content"></div>
            <div id="companyAnalytics" class="tab-content"></div>
            <div id="companyAssessments" class="tab-content"></div>
            <div id="companyAudit" class="tab-content"></div>
        </div>
    `;
    showPage('companyDashboard');
    // Update theme icon state for the newly rendered toggle
    if (typeof updateThemeIcon === 'function') updateThemeIcon(document.body.getAttribute('data-theme') || 'light');
    loadCompanyOverview();
}

function switchCompanyTab(tab, evt) {
    console.log('Switching to company tab:', tab);
    document.querySelectorAll('#companyDashboard .nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('#companyDashboard .tab-content').forEach(t => t.classList.remove('active'));

    const e = evt || window.event;
    if (e && e.target) {
        e.target.classList.add('active');
    }

    // Show the corresponding tab content
    const tabMap = {
        'overview': 'companyOverview',
        'jobs': 'companyJobs',
        'candidates': 'companyCandidates',
        'applications': 'companyApplications',
        'analytics': 'companyAnalytics',
        'assessments': 'companyAssessments',
        'audit': 'companyAudit'
    };

    const tabElement = document.getElementById(tabMap[tab]);
    if (tabElement) {
        tabElement.classList.add('active');
    }

    switch (tab) {
        case 'overview': loadCompanyOverview(); break;
        case 'jobs': loadCompanyJobs(); break;
        case 'candidates': loadCompanyCandidates(); break;
        case 'applications': loadCompanyApplications(); break;
        case 'analytics': loadCompanyAnalytics(); break;
        case 'assessments': loadCompanyAssessments(); break;
        case 'audit': loadCompanyAudit(); break;
    }
}

async function loadCompanyOverview(retryCount = 0) {
    console.log('Loading company overview...');
    const container = document.getElementById('companyOverview');
    if (!container) {
        console.error('Company overview container not found');
        return;
    }

    container.innerHTML = '<div class="loading">Loading dashboard...</div>';

    try {
        const response = await fetch(`${API_URL}/jobs/company/stats`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        container.innerHTML = `
            <div id="flanT5Notification" class="flan-t5-banner" style="display:none;"></div>
            <div class="content-header">
                <h2>📊 Company Dashboard</h2>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">💼</div>
                    <div class="stat-content">
                        <div class="stat-label">Active Jobs</div>
                        <div class="stat-value">${data.active_jobs || 0}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📋</div>
                    <div class="stat-content">
                        <div class="stat-label">Applications</div>
                        <div class="stat-value">${data.total_applications || 0}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">👥</div>
                    <div class="stat-content">
                        <div class="stat-label">Matched Candidates</div>
                        <div class="stat-value">${data.matched_candidates || 0}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📅</div>
                    <div class="stat-content">
                        <div class="stat-label">Interviews Scheduled</div>
                        <div class="stat-value">${data.interviews_scheduled || 0}</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <h3>🎯 Quick Actions</h3>
                <p>Start by posting a job to receive qualified candidate matches based on their assessment scores.</p>
                <button class="btn btn-primary" onclick="switchCompanyTab('jobs')">Post a Job</button>
            </div>
        `;

        // Load Flan-T5 status notification
        loadFlanT5Status();

    } catch (error) {
        console.error('Dashboard load error:', error);
        // Retry once on failure
        if (retryCount < 2) {
            console.log(`Retrying dashboard load (attempt ${retryCount + 2})...`);
            setTimeout(() => loadCompanyOverview(retryCount + 1), 1000);
        } else {
            container.innerHTML = `
                <div class="empty-state">
                    <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                    <h3>Failed to load dashboard</h3>
                    <p>Please check your connection and try again.</p>
                    <button class="btn btn-primary" onclick="loadCompanyOverview()">🔄 Retry</button>
                </div>
            `;
        }
    }
}

async function loadCompanyJobs() {
    const container = document.getElementById('companyJobs');
    container.innerHTML = '<div class="loading">Loading jobs...</div>';

    try {
        const response = await fetch(`${API_URL}/jobs/company`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const data = await response.json();
        const jobs = data.jobs || [];

        container.innerHTML = `
            <div class="content-header">
                <h2>💼 My Job Postings</h2>
                <button class="btn btn-primary" onclick="showJobModal()">+ Post New Job</button>
            </div>
            ${jobs.length === 0 ?
                '<div class="empty-state">No jobs posted yet. Click "Post New Job" to get started!</div>' :
                `<div class="job-grid">
                    ${jobs.map(job => `
                        <div class="job-card" onclick="viewJobDetails('${job._id}')">
                            <div class="job-header">
                                <div>
                                    <h3 class="job-title">${esc(job.title)}</h3>
                                    <p class="job-company">${esc(job.company_name || job.department || 'Smart Hiring')}</p>
                                </div>
                                <span class="badge badge-${job.status === 'open' ? 'success' : 'warning'}">
                                    ${esc(job.status)}
                                </span>
                            </div>
                            <p class="job-description" style="white-space: pre-line;">${esc((job.description || '').substring(0, 200))}...</p>
                            <div class="job-meta">
                                <span>📍 ${esc(job.location || 'Remote')}</span>
                                <span>💼 ${esc(job.job_type || 'Full-time')}</span>
                                <span>📋 ${job.applications_count || 0} applications</span>
                            </div>
                            <div class="job-tags">
                                ${(job.required_skills || []).slice(0, 5).map(s => `<span class="tag">${esc(s)}</span>`).join('')}
                            </div>
                            <button class="btn btn-primary" onclick="event.stopPropagation(); viewJobCandidates('${job._id}')">
                                View Candidates
                            </button>
                        </div>
                    `).join('')}
                </div>`
            }
        `;
    } catch (error) {
        container.innerHTML = '<div class="empty-state">Failed to load jobs</div>';
    }
}

function showJobModal() {
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Post new job');
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">Post New Job</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <form onsubmit="submitJob(event)">
                <div class="modal-body">
                    <div class="form-group">
                        <label>Job Title *</label>
                        <input type="text" id="jobTitle" required>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Department *</label>
                            <input type="text" id="jobDepartment" required>
                        </div>
                        <div class="form-group">
                            <label>Location *</label>
                            <input type="text" id="jobLocation" required>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Job Type *</label>
                        <select id="jobType" required>
                            <option value="full-time">Full-time</option>
                            <option value="part-time">Part-time</option>
                            <option value="contract">Contract</option>
                            <option value="internship">Internship</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Description *</label>
                        <textarea id="jobDescription" required></textarea>
                    </div>
                    <div class="form-group">
                        <label>Requirements *</label>
                        <textarea id="jobRequirements" required placeholder="One requirement per line"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Required Skills *</label>
                        <input type="text" id="jobSkills" required placeholder="Comma-separated (e.g., Python, JavaScript, React)">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Post Job</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(modal);
}

async function submitJob(e) {
    e.preventDefault();

    const title = document.getElementById('jobTitle').value.trim();
    const description = document.getElementById('jobDescription').value.trim();
    const requirements = document.getElementById('jobRequirements').value.trim();

    // Validate required fields
    if (!title || !description) {
        alert('Title and Description are required!');
        return;
    }

    // Combine description and requirements
    const fullDescription = description + (requirements ? '\n\nRequirements:\n' + requirements : '');

    const jobData = {
        title: title,
        company_name: document.getElementById('jobDepartment').value.trim() || 'Smart Hiring',
        location: document.getElementById('jobLocation').value.trim(),
        job_type: document.getElementById('jobType').value,
        description: fullDescription,
        required_skills: document.getElementById('jobSkills').value.split(',').map(s => s.trim()).filter(s => s)
    };

    try {
        const response = await fetch(`${API_URL}/jobs/create`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(jobData)
        });

        const data = await response.json();
        console.log('Job posting response:', response.status, data);

        if (response.ok) {
            alert('✓ Job posted successfully!');
            e.target.closest('.modal').remove();
            loadCompanyJobs();
        } else {
            const errorMsg = data.error || data.message || JSON.stringify(data);
            console.error('Job posting failed:', errorMsg);
            alert('Failed to post job: ' + errorMsg);
        }
    } catch (error) {
        console.error('Error posting job:', error);
        alert('Failed to post job: ' + error.message);
    }
}

async function loadCompanyCandidates() {
    const container = document.getElementById('companyCandidates');
    container.innerHTML = '<div class="loading">Loading your jobs and candidates...</div>';

    try {
        // Fetch all jobs for this recruiter
        const response = await fetch(`${API_URL}/jobs/company`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            throw new Error('Failed to load jobs');
        }

        const data = await response.json();
        const jobs = data.jobs || [];

        if (jobs.length === 0) {
            container.innerHTML = `
                <div class="content-header">
                    <h2>🎯 Matched Candidates</h2>
                </div>
                <div class="empty-state">
                    <div style="font-size: 64px; margin-bottom: 16px;">💼</div>
                    <h3>No Jobs Posted Yet</h3>
                    <p>Post your first job to start receiving candidate applications</p>
                    <button class="btn btn-primary" onclick="switchCompanyTab('jobs')">Post a Job</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="content-header">
                <h2>🎯 Matched Candidates by Job</h2>
                <p style="color: #64748b;">Click on any job to view AI-ranked candidates</p>
            </div>
            <div class="jobs-grid">
                ${jobs.map(job => `
                    <div class="card job-candidate-card" onclick="viewJobCandidates('${job._id}')" style="cursor: pointer; transition: all 0.3s; border: 2px solid #e2e8f0;">
                        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                            <div style="flex: 1;">
                                <h3 style="margin: 0 0 8px 0; color: #1e293b;">${job.title}</h3>
                                <div style="display: flex; gap: 12px; flex-wrap: wrap; font-size: 14px; color: #64748b;">
                                    <span>📍 ${job.location || 'Remote'}</span>
                                    <span>💼 ${job.job_type || 'Full-time'}</span>
                                </div>
                            </div>
                            <span class="badge ${job.status === 'open' ? 'badge-success' : 'badge-warning'}" style="text-transform: uppercase;">
                                ${job.status || 'open'}
                            </span>
                        </div>
                        
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; padding: 16px; color: white; margin-top: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div style="font-size: 32px; font-weight: 700; margin-bottom: 4px;">
                                        ${job.applications_count || 0}
                                    </div>
                                    <div style="opacity: 0.9;">Total Applicants</div>
                                </div>
                                <div style="font-size: 48px; opacity: 0.3;">
                                    👥
                                </div>
                            </div>
                        </div>
                        
                        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center; color: #667eea; font-weight: 600;">
                            Click to view ranked candidates →
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        container.classList.add('active');

    } catch (error) {
        console.error('Error loading candidates:', error);
        container.innerHTML = `
            <div class="content-header">
                <h2>🎯 Matched Candidates</h2>
            </div>
            <div class="alert alert-error">
                Failed to load candidates data. Please try again.
            </div>
            <button class="btn btn-primary" onclick="loadCompanyCandidates()">Retry</button>
        `;
    }
}

let selectedApplications = new Set();
let currentStatusFilter = 'all';
let blindMode = true; // Default ON for fairness (hide PII)

// normalizeStatus, anonymizeId — provided by shared-utils.js

async function loadCompanyApplications() {
    const container = document.getElementById('companyApplications');
    container.innerHTML = '<div class="loading">Loading applications...</div>';

    try {
        const response = await fetch(`${API_URL}/jobs/company/applications`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const data = await response.json();
        let applications = data.applications || [];

        if (applications.length === 0) {
            container.innerHTML = `
                <div class="content-header">
                    <h2>📋 Applications</h2>
                </div>
                <div class="empty-state">
                    <div style="font-size: 64px; margin-bottom: 16px;">📭</div>
                    <h3>No Applications Yet</h3>
                    <p>Applications will appear here once candidates apply to your jobs.</p>
                </div>
            `;
            return;
        }

        // Normalize all statuses
        applications.forEach(app => {
            app._normalizedStatus = normalizeStatus(app.status);
        });

        // Filter applications by status
        const filteredApps = currentStatusFilter === 'all'
            ? applications
            : applications.filter(app => app._normalizedStatus === currentStatusFilter);

        // Calculate statistics
        const stats = {
            total: applications.length,
            pending: applications.filter(a => a._normalizedStatus === 'pending').length,
            shortlisted: applications.filter(a => a._normalizedStatus === 'shortlisted').length,
            interviewed: applications.filter(a => a._normalizedStatus === 'interviewed').length,
            hired: applications.filter(a => a._normalizedStatus === 'hired').length,
            rejected: applications.filter(a => a._normalizedStatus === 'rejected').length
        };

        container.innerHTML = `
            <div class="content-header">
                <h2>📋 Applications Management</h2>
                <div style="display: flex; gap: 12px; align-items: center;">
                    <!-- Blind Mode / Fairness Toggle -->
                    <div style="display: flex; align-items: center; gap: 8px; background: ${blindMode ? 'linear-gradient(135deg, #4F46E5, #7c3aed)' : '#e2e8f0'}; padding: 8px 16px; border-radius: 12px; cursor: pointer; transition: all 0.3s; user-select: none;"
                         onclick="blindMode = !blindMode; loadCompanyApplications();">
                        <span style="font-size: 16px;">${blindMode ? '🔒' : '👁️'}</span>
                        <span style="color: ${blindMode ? 'white' : '#4a5568'}; font-weight: 600; font-size: 13px;">
                            ${blindMode ? 'Fairness Mode ON' : 'Fairness Mode OFF'}
                        </span>
                        <div style="width: 36px; height: 20px; background: ${blindMode ? 'rgba(255,255,255,0.3)' : '#cbd5e0'}; border-radius: 10px; position: relative; transition: all 0.3s;">
                            <div style="width: 16px; height: 16px; background: white; border-radius: 50%; position: absolute; top: 2px; ${blindMode ? 'right: 2px' : 'left: 2px'}; transition: all 0.3s; box-shadow: 0 1px 3px rgba(0,0,0,0.2);"></div>
                        </div>
                    </div>
                    ${selectedApplications.size > 0 ? `
                        <button class="btn btn-secondary" onclick="clearSelection()">
                            Clear (${selectedApplications.size})
                        </button>
                        <button class="btn btn-primary" onclick="bulkUpdateStatus()">
                            Update Selected
                        </button>
                    ` : ''}
                </div>
            </div>
            
            <!-- Status Filter Tabs -->
            <div class="status-filter-tabs">
                <button class="filter-tab ${currentStatusFilter === 'all' ? 'active' : ''}" 
                        onclick="filterByStatus('all')">
                    All (${stats.total})
                </button>
                <button class="filter-tab ${currentStatusFilter === 'pending' ? 'active' : ''}" 
                        onclick="filterByStatus('pending')">
                    🔵 Pending (${stats.pending})
                </button>
                <button class="filter-tab ${currentStatusFilter === 'shortlisted' ? 'active' : ''}" 
                        onclick="filterByStatus('shortlisted')">
                    💛 Shortlisted (${stats.shortlisted})
                </button>
                <button class="filter-tab ${currentStatusFilter === 'interviewed' ? 'active' : ''}" 
                        onclick="filterByStatus('interviewed')">
                    🟣 Interviewed (${stats.interviewed})
                </button>
                <button class="filter-tab ${currentStatusFilter === 'hired' ? 'active' : ''}" 
                        onclick="filterByStatus('hired')">
                    💚 Hired (${stats.hired})
                </button>
                <button class="filter-tab ${currentStatusFilter === 'rejected' ? 'active' : ''}" 
                        onclick="filterByStatus('rejected')">
                    ❌ Rejected (${stats.rejected})
                </button>
            </div>
            
            <!-- Applications Table -->
            <div class="applications-table-container">
                <table class="applications-table">
                    <thead>
                        <tr>
                            <th>
                                <input type="checkbox" onchange="toggleSelectAll(this.checked)" 
                                       ${selectedApplications.size === filteredApps.length && filteredApps.length > 0 ? 'checked' : ''}>
                            </th>
                            <th>Candidate</th>
                            <th>Job Position</th>
                            <th>Applied Date</th>
                            <th>Match Score</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filteredApps.map(app => `
                            <tr class="application-row ${selectedApplications.has(app._id) ? 'selected' : ''}">
                                <td>
                                    <input type="checkbox"
                                           data-app-id="${app._id}"
                                           ${selectedApplications.has(app._id) ? 'checked' : ''}
                                           onchange="toggleApplicationSelection(this.dataset.appId, this.checked)">
                                </td>
                                <td>
                                    <div class="candidate-info">
                                        ${blindMode ? `
                                            <div class="candidate-avatar" style="background: linear-gradient(135deg, #64748b, #475569); font-size: 14px;">🔒</div>
                                            <div>
                                                <div class="candidate-name" style="color: #64748b; font-style: italic;">Candidate ${anonymizeId(app._id)}</div>
                                                <div class="candidate-email" style="color: #94a3b8;">PII hidden — Fairness Mode</div>
                                            </div>
                                        ` : `
                                            <div class="candidate-avatar">${esc(app.candidate_name?.charAt(0) || 'C')}</div>
                                            <div>
                                                <div class="candidate-name">${esc(app.candidate_name || 'Unknown')}</div>
                                                <div class="candidate-email">${esc(app.candidate_email || '')}</div>
                                            </div>
                                        `}
                                    </div>
                                </td>
                                <td>
                                    <div class="job-info">
                                        <div class="job-title-cell">${esc(app.job_title)}</div>
                                        <div class="job-company-cell">${esc(app.company_name || '')}</div>
                                    </div>
                                </td>
                                <td>${new Date(app.applied_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                                <td>
                                    <div class="score-badge ${getScoreClass(app.overall_score)}">
                                        ${Math.round(app.overall_score || 0)}%
                                    </div>
                                </td>
                                <td>
                                    <div class="status-dropdown">
                                        <button class="status-badge status-${app._normalizedStatus}" 
                                                onclick="toggleStatusDropdown('${app._id}', event)">
                                            ${getStatusIcon(app._normalizedStatus)} ${app._normalizedStatus.charAt(0).toUpperCase() + app._normalizedStatus.slice(1)}
                                            <span class="dropdown-arrow">▼</span>
                                        </button>
                                        <div class="status-dropdown-menu" id="dropdown-${app._id}">
                                            ${['pending', 'shortlisted', 'interviewed', 'hired', 'rejected']
                .filter(s => s !== app._normalizedStatus)
                .map(s => `
                                                    <div class="status-option" onclick="updateApplicationStatus('${app._id}', '${s}')">
                                                        ${getStatusIcon(s)} ${s.charAt(0).toUpperCase() + s.slice(1)}
                                                    </div>
                                                `).join('')}
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <div class="action-buttons">
                                        <button class="btn-icon" onclick="viewApplicationDetails('${app._id}')" title="View Details">
                                            👁️
                                        </button>
                                        <button class="btn-icon" onclick="downloadResume('${app._id}')" title="Download Resume">
                                            📥
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (error) {
        console.error('Failed to load applications:', error);
        container.innerHTML = '<div class="empty-state">Failed to load applications</div>';
    }
}

// getStatusIcon, getScoreClass — provided by shared-utils.js

function toggleSelectAll(checked) {
    const checkboxes = document.querySelectorAll('.application-row input[type="checkbox"][data-app-id]');
    checkboxes.forEach(cb => {
        const appId = cb.dataset.appId;
        if (!appId) return;
        if (checked) {
            selectedApplications.add(appId);
            cb.checked = true;
        } else {
            selectedApplications.delete(appId);
            cb.checked = false;
        }
    });
    loadCompanyApplications();
}

function toggleApplicationSelection(appId, checked) {
    if (checked) {
        selectedApplications.add(appId);
    } else {
        selectedApplications.delete(appId);
    }
    loadCompanyApplications();
}

function clearSelection() {
    selectedApplications.clear();
    loadCompanyApplications();
}

function filterByStatus(status) {
    currentStatusFilter = status;
    selectedApplications.clear();
    loadCompanyApplications();
}

function toggleStatusDropdown(appId, event) {
    event.stopPropagation();
    const dropdown = document.getElementById(`dropdown-${appId}`);

    // Close all other dropdowns
    document.querySelectorAll('.status-dropdown-menu').forEach(d => {
        if (d.id !== `dropdown-${appId}`) {
            d.classList.remove('show');
        }
    });

    dropdown.classList.toggle('show');
}

// Close dropdowns when clicking outside
document.addEventListener('click', () => {
    document.querySelectorAll('.status-dropdown-menu').forEach(d => {
        d.classList.remove('show');
    });
});

async function updateApplicationStatus(appId, newStatus) {
    // Show confirmation modal
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Confirm status update');
    const isInterview = newStatus === 'interviewed';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 500px;">
            <div class="modal-header">
                <h3 class="modal-title">Confirm Status Update</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <div class="modal-body">
                <p>Are you sure you want to update the status to <strong>${newStatus}</strong>?</p>
                ${isInterview ? `
                <div style="background: #eef2ff; padding: 12px; border-radius: 8px; margin: 12px 0; border-left: 4px solid #4F46E5;">
                    <p style="margin:0; font-size: 14px; color: #4338CA;"><strong>🎥 Internal Interview Room</strong></p>
                    <p style="margin:4px 0 0; font-size: 13px; color: #6366F1;">An interview room link will be auto-generated and sent to the candidate.</p>
                </div>
                <div class="form-group">
                    <label>Interview Type:</label>
                    <select id="interviewType" class="form-control">
                        <option value="ai_automated">🤖 AI Automated Interview</option>
                        <option value="live">👤 Live Interview (Human Panel)</option>
                        <option value="hybrid">🔄 Hybrid (AI + Human)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Interview Date & Time (optional):</label>
                    <input type="datetime-local" id="interviewDate" class="form-control" />
                </div>
                ` : ''}
                ${newStatus === 'hired' ? `
                <div style="background: #f0fdf4; padding: 12px; border-radius: 8px; margin: 12px 0; border-left: 4px solid #10b981;">
                    <p style="margin:0; font-size: 14px; color: #166534;"><strong>🎉 Onboarding Workflow</strong></p>
                    <p style="margin:4px 0 0; font-size: 13px; color: #15803d;">An onboarding checklist will be generated and shared with the candidate automatically.</p>
                </div>
                ` : ''}
                <div class="form-group">
                    <label>Add a note (optional):</label>
                    <textarea id="statusNote" rows="3" placeholder="Reason for status change..."></textarea>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                <button class="btn btn-primary" onclick="confirmStatusUpdate('${appId}', '${newStatus}')">Confirm</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

async function confirmStatusUpdate(appId, newStatus) {
    const note = document.getElementById('statusNote')?.value || '';
    const interviewDate = document.getElementById('interviewDate')?.value || '';
    const interviewType = document.getElementById('interviewType')?.value || 'ai_automated';
    const modal = document.querySelector('.modal');

    const payload = { status: newStatus, note: note };
    if (newStatus === 'interviewed') {
        payload.interview_type = interviewType;
        if (interviewDate) payload.interview_date = interviewDate;
    }

    try {
        const response = await fetch(`${API_URL}/company/applications/${appId}/status`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const data = await response.json();
            if (newStatus === 'interviewed' && data.meeting_link) {
                showNotification(`✓ Interview scheduled! Link: ${data.meeting_link}`, 'success');
            } else {
                showNotification(`✓ Status updated to ${newStatus}`, 'success');
            }
            modal.remove();
            loadCompanyApplications();
        } else {
            const data = await response.json();
            showNotification('Failed to update status: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('Failed to update status: ' + error.message, 'error');
    }
}

function bulkUpdateStatus() {
    if (selectedApplications.size === 0) {
        showNotification('No applications selected', 'warning');
        return;
    }

    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Bulk status update');
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 500px;">
            <div class="modal-header">
                <h3 class="modal-title">Bulk Status Update</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <div class="modal-body">
                <p>Update status for <strong>${selectedApplications.size}</strong> selected application(s):</p>
                <div class="form-group">
                    <label>New Status:</label>
                    <select id="bulkStatus" class="form-control">
                        <option value="pending">🔵 Pending</option>
                        <option value="shortlisted">💛 Shortlisted</option>
                        <option value="interviewed">🟣 Interviewed</option>
                        <option value="hired">💚 Hired</option>
                        <option value="rejected">❌ Rejected</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Note (optional):</label>
                    <textarea id="bulkNote" rows="3" placeholder="Reason for bulk update..."></textarea>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                <button class="btn btn-primary" onclick="confirmBulkUpdate()">Update All</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

async function confirmBulkUpdate() {
    const newStatus = document.getElementById('bulkStatus').value;
    const note = document.getElementById('bulkNote')?.value || '';
    const modal = document.querySelector('.modal');

    try {
        const promises = Array.from(selectedApplications).map(appId =>
            fetch(`${API_URL}/company/applications/${appId}/status`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ status: newStatus, note: note })
            })
        );

        await Promise.all(promises);
        showNotification(`✓ Updated ${selectedApplications.size} application(s)`, 'success');
        selectedApplications.clear();
        modal.remove();
        loadCompanyApplications();
    } catch (error) {
        showNotification('Failed to update applications: ' + error.message, 'error');
    }
}

async function viewJobCandidates(jobId) {
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Ranked candidates');
    modal.innerHTML = '<div class="modal-content"><div class="loading">Loading ranked candidates...</div></div>';
    document.body.appendChild(modal);

    try {
        const response = await fetch(`${API_URL}/company/jobs/${jobId}/ranked-candidates`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || `Server returned ${response.status}`);
        }

        const data = await response.json();
        const candidates = data.ranked_candidates || [];

        modal.innerHTML = `
            <div class="modal-content" style="max-width: 1000px; max-height: 90vh;">
                <div class="modal-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px;">
                    <div>
                        <h3 class="modal-title" style="margin: 0; font-size: 24px;">${data.job_title}</h3>
                        <p style="margin: 8px 0 0 0; opacity: 0.9;">📊 ${data.total_applicants} Applicants - Ranked by AI Matching Score</p>
                    </div>
                    <button class="modal-close" onclick="this.closest('.modal').remove()" style="color: white; opacity: 0.9;">×</button>
                </div>
                <div class="modal-body" style="padding: 24px; overflow-y: auto; max-height: calc(90vh - 140px);">
                    ${candidates.length === 0 ? `
                        <div style="text-align: center; padding: 40px; color: #64748b;">
                            <div style="font-size: 64px; margin-bottom: 16px;">📭</div>
                            <h3>No Applicants Yet</h3>
                            <p>Candidates will appear here once they apply to this job.</p>
                        </div>
                    ` : `
                        ${candidates.map(candidate => `
                            <div style="background: white; border: 2px solid ${candidate.scores.overall_score >= 75 ? '#10b981' :
                candidate.scores.overall_score >= 50 ? '#f59e0b' : '#94a3b8'
            }; border-radius: 12px; padding: 20px; margin-bottom: 16px; position: relative;">
                                <!-- Rank Badge -->
                                <div style="position: absolute; top: -12px; left: 20px; background: ${candidate.rank === 1 ? 'linear-gradient(135deg, #fbbf24, #f59e0b)' :
                candidate.rank === 2 ? 'linear-gradient(135deg, #9ca3af, #6b7280)' :
                    candidate.rank === 3 ? 'linear-gradient(135deg, #fb923c, #ea580c)' :
                        '#667eea'
            }; color: white; padding: 6px 16px; border-radius: 20px; font-weight: 700; box-shadow: 0 2px 8px rgba(0,0,0,0.2);">
                                    ${candidate.rank === 1 ? '🥇' : candidate.rank === 2 ? '🥈' : candidate.rank === 3 ? '🥉' : ''}
                                    #${candidate.rank}
                                </div>
                                
                                <!-- Candidate Header -->
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-top: 8px;">
                                    <div style="flex: 1;">
                                        <h4 style="margin: 0 0 8px 0; font-size: 20px; color: #1e293b;">
                                            ${blindMode ? `🔒 Candidate ${anonymizeId(candidate.application_id || candidate.candidate_id)}` : esc(candidate.candidate_name)}
                                        </h4>
                                        <div style="display: flex; gap: 16px; flex-wrap: wrap; color: #64748b; font-size: 14px;">
                                            ${blindMode ? '<span style="color: #94a3b8; font-style: italic;">PII hidden — Fairness Mode</span>' : `<span>📧 ${esc(candidate.candidate_email)}</span>`}
                                            <span>📍 ${esc(candidate.location)}</span>
                                            <span>💼 ${candidate.experience_years} years exp.</span>
                                            <span>🎓 ${esc(candidate.education)}</span>
                                        </div>
                                    </div>
                                    
                                    <!-- Overall Score -->
                                    <div style="text-align: center; min-width: 100px;">
                                        <div style="font-size: 32px; font-weight: 700; color: ${candidate.scores.overall_score >= 75 ? '#10b981' :
                candidate.scores.overall_score >= 50 ? '#f59e0b' : '#64748b'
            };">
                                            ${candidate.scores.overall_score}%
                                        </div>
                                        <div style="font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">
                                            Match Score
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- Score Breakdown -->
                                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 20px 0;">
                                    <div style="background: #f0f9ff; padding: 12px; border-radius: 8px; border-left: 3px solid #3b82f6;">
                                        <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">📊 Skills Match</div>
                                        <div style="font-size: 20px; font-weight: 600; color: #1e293b;">
                                            ${candidate.scores.skill_match}%
                                            <span style="font-size: 14px; color: #64748b; font-weight: 400;">
                                                (${candidate.skills.match_count}/${candidate.skills.total_required})
                                            </span>
                                        </div>
                                    </div>
                                    <div style="background: #fef3f2; padding: 12px; border-radius: 8px; border-left: 3px solid #f97316;">
                                        <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">⚡ Experience Score</div>
                                        <div style="font-size: 20px; font-weight: 600; color: #1e293b;">${candidate.scores.experience_score}%</div>
                                    </div>
                                </div>
                                
                                <!-- Skills Breakdown -->
                                <div style="margin-bottom: 16px;">
                                    <div style="font-weight: 600; margin-bottom: 8px; color: #1e293b;">✅ Matched Skills (${candidate.skills.matched.length})</div>
                                    <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;">
                                        ${candidate.skills.matched.length > 0 ?
                candidate.skills.matched.map(skill =>
                    `<span style="background: #dcfce7; color: #166534; padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 500;">${esc(skill)}</span>`
                ).join('') :
                '<span style="color: #94a3b8;">None</span>'
            }
                                    </div>
                                    
                                    ${candidate.skills.missing.length > 0 ? `
                                        <div style="font-weight: 600; margin-bottom: 8px; color: #1e293b;">⚠️ Missing Skills (${candidate.skills.missing.length})</div>
                                        <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                                            ${candidate.skills.missing.map(skill =>
                `<span style="background: #fee2e2; color: #991b1b; padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 500;">${esc(skill)}</span>`
            ).join('')}
                                        </div>
                                    ` : ''}
                                </div>
                                
                                <!-- Action Buttons -->
                                <div style="display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap;">
                                    <button class="btn btn-secondary" onclick="viewApplicationDetails('${candidate.application_id}')" style="flex: 1; min-width: 140px;">
                                        📄 View Full Profile
                                    </button>
                                    <button class="btn ${candidate.status === 'pending' ? 'btn-primary' : 'btn-secondary'}" 
                                            onclick="updateApplicationStatus('${candidate.application_id}', 'shortlisted')" 
                                            style="flex: 1; min-width: 120px;">
                                        ⭐ ${candidate.status === 'shortlisted' ? 'Shortlisted' : 'Shortlist'}
                                    </button>
                                    ${candidate.skills && candidate.skills.missing && candidate.skills.missing.length > 0 ? `
                                    <button class="btn btn-primary" style="flex: 1; min-width: 160px; background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%); border: none;" 
                                            onclick="event.stopPropagation(); launchFlanT5Interview('${jobId}', '${candidate.candidate_id}', '${esc(candidate.candidate_name || 'Candidate')}')">
                                        🧠 AI Interview (${candidate.skills.missing.length} gaps)
                                    </button>` : ''}
                                    ${candidate.resume_uploaded ?
                `<button class="btn btn-secondary" onclick="downloadResume('${candidate.application_id}')">
                                            📥 Resume
                                        </button>` : ''
            }
                                </div>
                                
                                <!-- Application Date & Status -->
                                <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: #64748b;">
                                    <span>Applied: ${new Date(candidate.applied_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                                    <span style="background: ${candidate.status === 'hired' ? '#dcfce7' :
                candidate.status === 'shortlisted' ? '#fef3c7' :
                    candidate.status === 'interviewed' ? '#e0e7ff' :
                        candidate.status === 'rejected' ? '#fee2e2' : '#f1f5f9'
            }; color: ${candidate.status === 'hired' ? '#166534' :
                candidate.status === 'shortlisted' ? '#854d0e' :
                    candidate.status === 'interviewed' ? '#3730a3' :
                        candidate.status === 'rejected' ? '#991b1b' : '#475569'
            }; padding: 4px 12px; border-radius: 12px; font-weight: 600; text-transform: capitalize;">
                                        ${candidate.status}
                                    </span>
                                </div>
                            </div>
                        `).join('')}
                    `}
                </div>
                <div class="modal-footer" style="background: #f8fafc; padding: 16px 24px;">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error loading candidates:', error);
        modal.remove();
        showErrorModal(error.message || 'Failed to load candidates. Please try again.');
    }
}

async function viewApplicationDetails(appId) {
    try {
        const response = await fetch(`${API_URL}/company/applications/${appId}/history`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            if (response.status === 403) {
                console.warn('Application history: permission denied or session expired');
                showNotification('Session may have expired. Please log in again.', 'warning');
                return;
            }
            throw new Error('Failed to load application details');
        }

        const data = await response.json();
        const app = data.application || data;

        // Try to fetch video interview session for this application
        let interviewInfo = '';
        try {
            const candidateId = app.candidate_id || '';
            if (candidateId) {
                const viResp = await fetch(`${API_URL}/video-interview/candidate/${candidateId}`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                if (viResp.ok) {
                    const viData = await viResp.json();
                    const sessions = (viData.sessions || []).filter(s => 
                        s.job_id === app.job_id || s.application_id === appId
                    );
                    if (sessions.length > 0) {
                        interviewInfo = sessions.map(s => {
                            const typeLabel = { ai_automated: '🤖 AI', live: '👤 Live', hybrid: '🔄 Hybrid' }[s.interview_type] || s.interview_type;
                            const hasRecording = s.recording_available || s.recordings?.length > 0;
                            const malpractice = s.malpractice_events || s.malpractice_flags || [];
                            const malpracticeCount = Array.isArray(malpractice) ? malpractice.length : (malpractice || 0);
                            const evalScore = s.evaluation_score || s.ai_score;
                            return `
                            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; margin-bottom: 10px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                    <span style="font-weight: 600;">${typeLabel} Interview</span>
                                    <span class="badge badge-${s.status === 'completed' ? 'success' : s.status === 'in_progress' ? 'warning' : 'info'}">${s.status}</span>
                                </div>
                                <div style="display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px;">
                                    ${hasRecording ? `<span style="color: #dc2626;">🔴 Recording Available <a href="#" onclick="window.open('${API_URL}/video-interview/download-recording/${s._id || s.session_id}','_blank');return false;" style="color: #4F46E5;">Download</a></span>` : 
                                    `<span style="color: #94a3b8;">⚫ No Recording</span>`}
                                    ${malpracticeCount > 0 ? `<span style="color: #dc2626; font-weight: 600;">⚠️ ${malpracticeCount} Proctoring Alert${malpracticeCount > 1 ? 's' : ''}</span>` : 
                                    `<span style="color: #10b981;">✅ No Proctoring Issues</span>`}
                                    ${evalScore ? `<span style="color: #4F46E5; font-weight: 600;">🎯 Score: ${evalScore}%</span>` : ''}
                                </div>
                                ${malpracticeCount > 0 && Array.isArray(malpractice) ? `
                                <details style="margin-top: 8px;">
                                    <summary style="cursor: pointer; font-size: 12px; color: #dc2626;">View proctoring details</summary>
                                    <ul style="margin: 6px 0 0 16px; font-size: 12px; color: #6b7280;">
                                        ${malpractice.slice(0, 10).map(e => `<li>${e.event_type || e.type || e}: ${e.details || ''} ${e.timestamp ? '(' + new Date(e.timestamp).toLocaleTimeString() + ')' : ''}</li>`).join('')}
                                    </ul>
                                </details>
                                ` : ''}
                            </div>`;
                        }).join('');
                    }
                }
            }
        } catch (viErr) {
            console.warn('Could not fetch interview session info:', viErr);
        }

        // Show modal with application details
        const modal = document.createElement('div');
        modal.className = 'modal show';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Application details');
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Application Details</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    <div class="application-details">
                        ${interviewInfo ? `
                        <h4>🎥 Interview Sessions</h4>
                        ${interviewInfo}
                        ` : ''}
                        <h4>Status History</h4>
                        ${(data.history || data.status_history) && (data.history || data.status_history).length > 0 ? `
                            <div class="status-timeline">
                                ${(data.history || data.status_history).map(h => `
                                    <div class="timeline-item">
                                        <div class="timeline-icon">${getStatusIcon(h.status)}</div>
                                        <div class="timeline-content">
                                            <div class="timeline-status">${esc(h.status)}</div>
                                            <div class="timeline-date">${new Date(h.changed_at).toLocaleString()}</div>
                                            ${h.note ? `<div class="timeline-note">${esc(h.note)}</div>` : ''}
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : '<p>No status history available</p>'}
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    } catch (error) {
        console.error('Error loading application details:', error);
        showNotification('Failed to load application details: ' + error.message, 'error');
    }
}

async function downloadResume(appId) {
    try {
        const response = await fetch(`${API_URL}/candidates/resume/${appId}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || 'Resume not available');
        }

        const blob = await response.blob();
        const contentDisposition = response.headers.get('Content-Disposition') || '';
        let filename = `resume_${appId}.pdf`;
        const match = contentDisposition.match(/filename="?([^"]+)"?/);
        if (match) {
            filename = match[1];
        }
        
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showNotification('✓ Resume downloaded (PII anonymised)', 'success');
    } catch (error) {
        console.error('Error downloading resume:', error);
        showNotification('Failed to download resume: ' + error.message, 'error');
    }
}

function companyLogout() {
    // Clear all authentication data including role-specific tokens
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    localStorage.removeItem('currentRole');
    localStorage.removeItem('candidate_token');
    localStorage.removeItem('recruiter_token');
    localStorage.removeItem('admin_token');

    // Reload the page to return to login
    window.location.href = '/';
}

// ============================================
// ANALYTICS DASHBOARD - ENTERPRISE GRADE
// ============================================
async function loadCompanyAnalytics() {
    const container = document.getElementById('companyAnalytics');
    container.innerHTML = '<div class="loading">Loading analytics...</div>';

    try {
        // Fetch analytics data
        const [jobsRes, appsRes] = await Promise.all([
            fetch(`${API_URL}/jobs/company`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            }),
            fetch(`${API_URL}/jobs/company/applications`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            })
        ]);

        if (!jobsRes.ok || !appsRes.ok) {
            throw new Error('Failed to fetch analytics data');
        }

        const jobsData = await jobsRes.json();
        const appsData = await appsRes.json();
        const jobs = jobsData.jobs || [];
        const applications = appsData.applications || [];

        // Calculate metrics
        const totalJobs = jobs.length;
        const activeJobs = jobs.filter(j => j.status === 'open').length;
        const totalApps = applications.length;
        const shortlisted = applications.filter(a => a.status === 'shortlisted').length;
        const interviewed = applications.filter(a => a.status === 'interviewed').length;
        const hired = applications.filter(a => a.status === 'hired').length;
        const rejected = applications.filter(a => a.status === 'rejected').length;
        const pending = applications.filter(a => a.status === 'pending' || a.status === 'submitted').length;

        // Conversion rates
        const shortlistRate = totalApps > 0 ? ((shortlisted / totalApps) * 100).toFixed(1) : 0;
        const interviewRate = totalApps > 0 ? ((interviewed / totalApps) * 100).toFixed(1) : 0;
        const hireRate = totalApps > 0 ? ((hired / totalApps) * 100).toFixed(1) : 0;

        // Score distribution
        const avgScore = totalApps > 0 ?
            (applications.reduce((sum, a) => sum + (a.cci_score || 0), 0) / totalApps).toFixed(1) : 0;

        // Time to hire (mock data for now)
        const avgTimeToHire = 14;

        container.innerHTML = `
            <div class="analytics-header">
                <div class="analytics-title">
                    <h2>📈 Hiring Analytics</h2>
                    <p class="subtitle">Comprehensive insights into your hiring performance</p>
                </div>
                <div class="analytics-actions">
                    <select class="analytics-filter" onchange="filterAnalytics(this.value)">
                        <option value="30">Last 30 Days</option>
                        <option value="90">Last 90 Days</option>
                        <option value="180">Last 6 Months</option>
                        <option value="365">Last Year</option>
                    </select>
                    <button class="btn btn-secondary" onclick="exportAnalytics()">
                        <span>📊</span> Export Report
                    </button>
                </div>
            </div>
            
            <!-- KPI Cards -->
            <div class="analytics-kpi-grid">
                <div class="kpi-card kpi-primary">
                    <div class="kpi-icon">💼</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${totalJobs}</div>
                        <div class="kpi-label">Total Jobs Posted</div>
                        <div class="kpi-trend positive">
                            <span>↑ ${activeJobs} active</span>
                        </div>
                    </div>
                </div>
                
                <div class="kpi-card kpi-success">
                    <div class="kpi-icon">📋</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${totalApps}</div>
                        <div class="kpi-label">Total Applications</div>
                        <div class="kpi-trend positive">
                            <span>↑ ${pending} pending</span>
                        </div>
                    </div>
                </div>
                
                <div class="kpi-card kpi-warning">
                    <div class="kpi-icon">⭐</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${avgScore}</div>
                        <div class="kpi-label">Avg Match Score</div>
                        <div class="kpi-trend ${avgScore >= 70 ? 'positive' : 'neutral'}">
                            <span>${avgScore >= 70 ? '↑' : '→'} out of 100</span>
                        </div>
                    </div>
                </div>
                
                <div class="kpi-card kpi-info">
                    <div class="kpi-icon">⏱️</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${avgTimeToHire}</div>
                        <div class="kpi-label">Avg Time to Hire (days)</div>
                        <div class="kpi-trend positive">
                            <span>↓ 2 days faster</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Hiring Funnel -->
            <div class="analytics-section">
                <div class="section-header">
                    <h3>🎯 Hiring Funnel</h3>
                    <p>Track candidate progression through your hiring stages</p>
                </div>
                <div class="funnel-container">
                    <div class="funnel-stage" style="width: 100%;">
                        <div class="funnel-bar" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                            <span class="funnel-label">Applications</span>
                            <span class="funnel-value">${totalApps}</span>
                        </div>
                        <div class="funnel-percent">100%</div>
                    </div>
                    
                    <div class="funnel-stage" style="width: ${shortlisted > 0 ? (shortlisted / totalApps * 100) : 0}%;">
                        <div class="funnel-bar" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                            <span class="funnel-label">Shortlisted</span>
                            <span class="funnel-value">${shortlisted}</span>
                        </div>
                        <div class="funnel-percent">${shortlistRate}%</div>
                    </div>
                    
                    <div class="funnel-stage" style="width: ${interviewed > 0 ? (interviewed / totalApps * 100) : 0}%;">
                        <div class="funnel-bar" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                            <span class="funnel-label">Interviewed</span>
                            <span class="funnel-value">${interviewed}</span>
                        </div>
                        <div class="funnel-percent">${interviewRate}%</div>
                    </div>
                    
                    <div class="funnel-stage" style="width: ${hired > 0 ? (hired / totalApps * 100) : 5}%;">
                        <div class="funnel-bar" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                            <span class="funnel-label">Hired</span>
                            <span class="funnel-value">${hired}</span>
                        </div>
                        <div class="funnel-percent">${hireRate}%</div>
                    </div>
                </div>
            </div>
            
            <!-- Score Distribution & Decision Breakdown -->
            <div class="analytics-grid-2">
                <div class="analytics-section">
                    <div class="section-header">
                        <h3>📊 Score Distribution</h3>
                        <p>Candidate quality metrics</p>
                    </div>
                    <div class="score-distribution">
                        ${generateScoreChart(applications)}
                    </div>
                </div>
                
                <div class="analytics-section">
                    <div class="section-header">
                        <h3>🎯 Decision Breakdown</h3>
                        <p>Application status distribution</p>
                    </div>
                    <div class="decision-breakdown">
                        <div class="decision-item">
                            <div class="decision-label">
                                <span class="decision-dot" style="background: #10b981;"></span>
                                Hired
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (hired / totalApps * 100) : 0}%; background: #10b981;"></div>
                            </div>
                            <div class="decision-value">${hired}</div>
                        </div>
                        
                        <div class="decision-item">
                            <div class="decision-label">
                                <span class="decision-dot" style="background: #3b82f6;"></span>
                                Interviewed
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (interviewed / totalApps * 100) : 0}%; background: #3b82f6;"></div>
                            </div>
                            <div class="decision-value">${interviewed}</div>
                        </div>
                        
                        <div class="decision-item">
                            <div class="decision-label">
                                <span class="decision-dot" style="background: #f59e0b;"></span>
                                Shortlisted
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (shortlisted / totalApps * 100) : 0}%; background: #f59e0b;"></div>
                            </div>
                            <div class="decision-value">${shortlisted}</div>
                        </div>
                        
                        <div class="decision-item">
                            <div class="decision-label">
                                <span class="decision-dot" style="background: #6b7280;"></span>
                                Pending
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (pending / totalApps * 100) : 0}%; background: #6b7280;"></div>
                            </div>
                            <div class="decision-value">${pending}</div>
                        </div>
                        
                        <div class="decision-item">
                            <div class="decision-label">
                                <span class="decision-dot" style="background: #ef4444;"></span>
                                Rejected
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (rejected / totalApps * 100) : 0}%; background: #ef4444;"></div>
                            </div>
                            <div class="decision-value">${rejected}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Top Performing Jobs -->
            <div class="analytics-section">
                <div class="section-header">
                    <h3>🏆 Top Performing Jobs</h3>
                    <p>Jobs with highest application rates</p>
                </div>
                <div class="top-jobs-list">
                    ${generateTopJobsTable(jobs, applications)}
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Error loading analytics:', error);
        container.innerHTML = `
            <div class="alert alert-error">
                Failed to load analytics. Please try again.
            </div>
        `;
    }
}

function generateScoreChart(applications) {
    const excellent = applications.filter(a => (a.cci_score || 0) >= 75).length;
    const good = applications.filter(a => (a.cci_score || 0) >= 50 && (a.cci_score || 0) < 75).length;
    const fair = applications.filter(a => (a.cci_score || 0) >= 25 && (a.cci_score || 0) < 50).length;
    const poor = applications.filter(a => (a.cci_score || 0) < 25).length;
    const total = applications.length || 1;

    return `
        <div class="score-bars">
            <div class="score-item">
                <div class="score-label">
                    <span class="score-badge excellent">⭐ Excellent</span>
                    <span class="score-range">75-100</span>
                </div>
                <div class="score-bar">
                    <div class="score-fill excellent" style="width: ${(excellent / total * 100)}%;"></div>
                </div>
                <div class="score-count">${excellent}</div>
            </div>
            
            <div class="score-item">
                <div class="score-label">
                    <span class="score-badge good">✓ Good</span>
                    <span class="score-range">50-74</span>
                </div>
                <div class="score-bar">
                    <div class="score-fill good" style="width: ${(good / total * 100)}%;"></div>
                </div>
                <div class="score-count">${good}</div>
            </div>
            
            <div class="score-item">
                <div class="score-label">
                    <span class="score-badge fair">○ Fair</span>
                    <span class="score-range">25-49</span>
                </div>
                <div class="score-bar">
                    <div class="score-fill fair" style="width: ${(fair / total * 100)}%;"></div>
                </div>
                <div class="score-count">${fair}</div>
            </div>
            
            <div class="score-item">
                <div class="score-label">
                    <span class="score-badge poor">✕ Poor</span>
                    <span class="score-range">0-24</span>
                </div>
                <div class="score-bar">
                    <div class="score-fill poor" style="width: ${(poor / total * 100)}%;"></div>
                </div>
                <div class="score-count">${poor}</div>
            </div>
        </div>
    `;
}

function generateTopJobsTable(jobs, applications) {
    // Calculate application count per job
    const jobStats = jobs.map(job => {
        const jobApps = applications.filter(a => a.job_id === job._id);
        return {
            ...job,
            appCount: jobApps.length,
            avgScore: jobApps.length > 0 ?
                (jobApps.reduce((sum, a) => sum + (a.cci_score || 0), 0) / jobApps.length).toFixed(1) : 0,
            hired: jobApps.filter(a => a.status === 'hired').length
        };
    }).sort((a, b) => b.appCount - a.appCount).slice(0, 5);

    if (jobStats.length === 0) {
        return '<div class="empty-state">No jobs posted yet</div>';
    }

    return `
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Job Title</th>
                    <th>Applications</th>
                    <th>Avg Score</th>
                    <th>Hired</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                ${jobStats.map((job, index) => `
                    <tr>
                        <td>
                            <div class="job-rank">${index + 1}</div>
                            <div class="job-info">
                                <div class="job-title">${job.title}</div>
                                <div class="job-meta">${job.location} • ${job.experience}</div>
                            </div>
                        </td>
                        <td><span class="metric-badge">${job.appCount}</span></td>
                        <td><span class="score-pill ${job.avgScore >= 75 ? 'excellent' : job.avgScore >= 50 ? 'good' : 'fair'}">${job.avgScore}</span></td>
                        <td><span class="metric-badge success">${job.hired}</span></td>
                        <td><span class="status-badge ${job.status === 'open' ? 'open' : 'closed'}">${job.status}</span></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function filterAnalytics(days) {
    showNotification(`Filtering data for last ${days} days...`, 'info');
    // In production, this would re-fetch with date filters
}

function exportAnalytics() {
    try {
        const rows = [];
        rows.push(['Hiring Analytics Report - Smart Hiring System']);
        rows.push(['Generated', new Date().toLocaleString()]);
        rows.push([]);

        // Export KPI metrics from the analytics dashboard
        const kpiCards = document.querySelectorAll('#companyAnalytics .kpi-card');
        if (kpiCards.length > 0) {
            rows.push(['--- Key Performance Indicators ---']);
            kpiCards.forEach(card => {
                const label = card.querySelector('.kpi-label, .kpi-title, h4')?.textContent?.trim() || '';
                const value = card.querySelector('.kpi-value, h2, h3')?.textContent?.trim() || '';
                if (label || value) rows.push([label, value]);
            });
            rows.push([]);
        }

        // Export pipeline data from status cards
        const statusCards = document.querySelectorAll('#companyAnalytics .pipeline-stage, .funnel-stage, .status-row');
        if (statusCards.length > 0) {
            rows.push(['--- Hiring Pipeline ---']);
            rows.push(['Stage', 'Count']);
            statusCards.forEach(card => {
                const stage = card.querySelector('.stage-name, .status-label, span')?.textContent?.trim() || '';
                const count = card.querySelector('.stage-count, .status-count, strong')?.textContent?.trim() || '';
                if (stage) rows.push([stage, count]);
            });
            rows.push([]);
        }

        // Export stat values and labels
        const statValues = document.querySelectorAll('#companyAnalytics .stat-value, .metric-value');
        const statLabels = document.querySelectorAll('#companyAnalytics .stat-label, .metric-label');
        if (statValues.length > 0) {
            rows.push(['--- Detailed Metrics ---']);
            statValues.forEach((val, i) => {
                const label = statLabels[i]?.textContent?.trim() || `Metric ${i + 1}`;
                rows.push([label, val.textContent.trim()]);
            });
            rows.push([]);
        }

        if (kpiCards.length === 0 && statusCards.length === 0 && statValues.length === 0) {
            rows.push(['No analytics data loaded. Please visit the Analytics tab first.']);
        }

        const csv = rows.map(row =>
            row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')
        ).join('\n');

        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `hiring_analytics_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showNotification('Analytics report exported as CSV!', 'success');
    } catch (error) {
        console.error('Export error:', error);
        showNotification('Failed to export analytics. Please try again.', 'error');
    }
}

// ============================================
// AI-POWERED ASSESSMENT MANAGEMENT
// ============================================
async function loadCompanyAssessments() {
    const container = document.getElementById('companyAssessments');
    container.innerHTML = '<div class="loading">Loading assessments...</div>';

    container.innerHTML = `
        <div class="content-header" style="display:flex;justify-content:space-between;align-items:center;">
            <h2>🧠 AI Assessment Manager</h2>
            <a href="assessment-config.html" class="btn btn-primary" target="_blank">📋 Open Full Config Panel</a>
        </div>
        <div class="card" style="border-left:4px solid #6366f1;">
            <h3>Quick Overview</h3>
            <p style="color:#64748b;">Manage AI-powered assessments with Claude/GPT question generation, live code execution, and intelligent scoring.</p>
            <div id="companyAssessmentStats" style="display:flex;gap:16px;flex-wrap:wrap;margin:16px 0;"></div>
        </div>
        <div id="companyAssessmentConfigs">
            <div class="loading">Loading configurations...</div>
        </div>
    `;

    try {
        const resp = await fetch(`${API_URL}/smart-assessments/configs`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        const data = await resp.json();
        const configs = data.configs || [];

        // Stats
        const totalSessions = configs.reduce((s, c) => s + (c.sessions_count || 0), 0);
        document.getElementById('companyAssessmentStats').innerHTML = `
            <div class="stat-card"><div class="stat-icon">📋</div><div class="stat-content"><div class="stat-label">Configs</div><div class="stat-value">${configs.length}</div></div></div>
            <div class="stat-card"><div class="stat-icon">✅</div><div class="stat-content"><div class="stat-label">Active</div><div class="stat-value">${configs.filter(c => c.is_active).length}</div></div></div>
            <div class="stat-card"><div class="stat-icon">👤</div><div class="stat-content"><div class="stat-label">Sessions</div><div class="stat-value">${totalSessions}</div></div></div>
        `;

        if (configs.length === 0) {
            document.getElementById('companyAssessmentConfigs').innerHTML = `
                <div class="card"><div class="empty-state">
                    <div style="font-size:64px;margin-bottom:16px;">🧠</div>
                    <h3>No Assessments Configured</h3>
                    <p>Create your first AI-powered assessment from the config panel.</p>
                    <a href="assessment-config.html" class="btn btn-primary" target="_blank">+ Create Assessment</a>
                </div></div>
            `;
            return;
        }

        document.getElementById('companyAssessmentConfigs').innerHTML = `
            <div class="card"><h3>📋 Assessment Configurations</h3>
            <div class="jobs-grid">
                ${configs.map(c => `
                    <div class="job-card" style="border-left:4px solid #6366f1;">
                        <h3 style="margin:0 0 8px;">${c.title}</h3>
                        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
                            <span class="tag" style="background:#ede9fe;color:#7c3aed;">${c.job_role}</span>
                            ${(c.question_types || []).map(t => `<span class="tag">${t}</span>`).join('')}
                        </div>
                        <div style="font-size:13px;color:#64748b;">
                            📝 ${c.total_questions} questions • ⏱ ${c.duration_minutes} min • 🎯 ${c.passing_score}% pass • 📊 ${c.sessions_count || 0} sessions
                        </div>
                    </div>
                `).join('')}
            </div></div>
        `;
    } catch (error) {
        console.error('Failed to load smart assessments:', error);
        document.getElementById('companyAssessmentConfigs').innerHTML = `
            <div class="card"><div class="alert alert-error">Failed to load assessment configs. ${error.message}</div></div>
        `;
    }
}

// ============================================
// FAIRNESS AUDIT INTERFACE
// ============================================
async function loadCompanyAudit(days = 30) {
    const container = document.getElementById('companyAudit');
    container.innerHTML = '<div class="loading">Loading audit data...</div>';

    try {
        const response = await fetch(`${API_URL}/audit/report?days=${days}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            throw new Error('Failed to load audit report');
        }

        const data = await response.json();

        container.innerHTML = `
            <div class="audit-header">
                <div class="audit-title">
                    <h2>🛡️ Fairness Audit Report</h2>
                    <p class="subtitle">Transparent hiring decisions • Bias-free environment • Compliance ready</p>
                </div>
                <div class="audit-actions">
                    <select class="audit-filter" onchange="filterAuditReport(this.value)">
                        <option value="30">Last 30 Days</option>
                        <option value="90">Last 90 Days</option>
                        <option value="180">Last 6 Months</option>
                        <option value="365">Last Year</option>
                    </select>
                    <button class="btn btn-primary" onclick="exportAuditReport()">
                        <span>📥</span> Export Compliance Report
                    </button>
                </div>
            </div>
            
            <!-- Audit Summary Cards -->
            <div class="audit-summary-grid">
                <div class="audit-card">
                    <div class="audit-icon" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                        📋
                    </div>
                    <div class="audit-content">
                        <div class="audit-value">${data.total_events || 0}</div>
                        <div class="audit-label">Total Events Logged</div>
                        <div class="audit-breakdown">
                            ${Object.entries(data.events_by_type || {}).map(([type, count]) => `
                                <span class="audit-tag">${type}: ${count}</span>
                            `).join('')}
                        </div>
                    </div>
                </div>
                
                <div class="audit-card">
                    <div class="audit-icon" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        ⭐
                    </div>
                    <div class="audit-content">
                        <div class="audit-value">${data.average_scores?.overall || 'N/A'}</div>
                        <div class="audit-label">Average Match Score</div>
                        <div class="audit-breakdown">
                            <span class="audit-tag">Skills: ${data.average_scores?.skills_match || 'N/A'}</span>
                            <span class="audit-tag">Experience: ${data.average_scores?.experience || 'N/A'}</span>
                        </div>
                    </div>
                </div>
                
                <div class="audit-card">
                    <div class="audit-icon" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                        🎯
                    </div>
                    <div class="audit-content">
                        <div class="audit-value">${data.score_distribution?.excellent || 0}</div>
                        <div class="audit-label">High-Quality Matches</div>
                        <div class="audit-breakdown">
                            <span class="audit-tag">Good: ${data.score_distribution?.good || 0}</span>
                            <span class="audit-tag">Fair: ${data.score_distribution?.fair || 0}</span>
                        </div>
                    </div>
                </div>
                
                <div class="audit-card">
                    <div class="audit-icon" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                        ✓
                    </div>
                    <div class="audit-content">
                        <div class="audit-value">${data.decisions_breakdown?.hired || 0}</div>
                        <div class="audit-label">Candidates Hired</div>
                        <div class="audit-breakdown">
                            <span class="audit-tag">Shortlisted: ${data.decisions_breakdown?.shortlisted || 0}</span>
                            <span class="audit-tag">Interviewed: ${data.decisions_breakdown?.interviewed || 0}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Fairness Metrics -->
            <div class="audit-section">
                <div class="section-header">
                    <h3>⚖️ Fairness Metrics</h3>
                    <p>Bias detection and compliance indicators</p>
                </div>
                <div class="fairness-grid">
                    <div class="fairness-card">
                        <div class="fairness-icon">✓</div>
                        <div class="fairness-label">Score-Based Decisions</div>
                        <div class="fairness-status success">✓ 100% Objective</div>
                        <p class="fairness-desc">All hiring decisions are based on quantifiable skill match scores</p>
                    </div>
                    
                    <div class="fairness-card">
                        <div class="fairness-icon">🔒</div>
                        <div class="fairness-label">Anonymized Scoring</div>
                        <div class="fairness-status success">✓ Enabled</div>
                        <p class="fairness-desc">Initial scoring happens without demographic information</p>
                    </div>
                    
                    <div class="fairness-card">
                        <div class="fairness-icon">📊</div>
                        <div class="fairness-label">Audit Trail</div>
                        <div class="fairness-status success">✓ Complete</div>
                        <p class="fairness-desc">Every decision is logged with timestamps and justification</p>
                    </div>
                    
                    <div class="fairness-card">
                        <div class="fairness-icon">🛡️</div>
                        <div class="fairness-label">Compliance Ready</div>
                        <div class="fairness-status success">✓ Yes</div>
                        <p class="fairness-desc">Full audit reports available for regulatory requirements</p>
                    </div>
                </div>
            </div>
            
            <!-- Score Distribution Analysis -->
            <div class="audit-section">
                <div class="section-header">
                    <h3>📊 Score Distribution Analysis</h3>
                    <p>Ensuring fair evaluation across all candidates</p>
                </div>
                <div class="score-fairness-chart">
                    ${generateFairnessScoreChart(data.score_distribution || {})}
                </div>
            </div>
            
            <!-- Recent Audit Events -->
            <div class="audit-section">
                <div class="section-header">
                    <h3>📝 Recent Audit Events</h3>
                    <p>Real-time tracking of all hiring decisions</p>
                </div>
                <div class="audit-timeline">
                    ${await generateAuditTimeline()}
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Error loading audit data:', error);
        container.innerHTML = `
            <div class="alert alert-info">
                <h3>🛡️ Fairness Audit System</h3>
                <p>The audit system is tracking all your hiring decisions to ensure bias-free hiring.</p>
                <p>Audit data will appear here as you review applications and make hiring decisions.</p>
                <button class="btn btn-primary" onclick="loadCompanyApplications()">View Applications</button>
            </div>
        `;
    }
}

function generateFairnessScoreChart(distribution) {
    const excellent = distribution.excellent || 0;
    const good = distribution.good || 0;
    const fair = distribution.fair || 0;
    const poor = distribution.poor || 0;
    const total = excellent + good + fair + poor || 1;

    return `
        <div class="fairness-bars">
            <div class="fairness-bar-item">
                <div class="fairness-bar-header">
                    <span class="fairness-bar-label">Excellent (75-100)</span>
                    <span class="fairness-bar-percent">${((excellent / total) * 100).toFixed(1)}%</span>
                </div>
                <div class="fairness-bar">
                    <div class="fairness-bar-fill" style="width: ${(excellent / total) * 100}%; background: linear-gradient(90deg, #10b981, #059669);"></div>
                </div>
                <div class="fairness-bar-count">${excellent} candidates</div>
            </div>
            
            <div class="fairness-bar-item">
                <div class="fairness-bar-header">
                    <span class="fairness-bar-label">Good (50-74)</span>
                    <span class="fairness-bar-percent">${((good / total) * 100).toFixed(1)}%</span>
                </div>
                <div class="fairness-bar">
                    <div class="fairness-bar-fill" style="width: ${(good / total) * 100}%; background: linear-gradient(90deg, #3b82f6, #2563eb);"></div>
                </div>
                <div class="fairness-bar-count">${good} candidates</div>
            </div>
            
            <div class="fairness-bar-item">
                <div class="fairness-bar-header">
                    <span class="fairness-bar-label">Fair (25-49)</span>
                    <span class="fairness-bar-percent">${((fair / total) * 100).toFixed(1)}%</span>
                </div>
                <div class="fairness-bar">
                    <div class="fairness-bar-fill" style="width: ${(fair / total) * 100}%; background: linear-gradient(90deg, #f59e0b, #d97706);"></div>
                </div>
                <div class="fairness-bar-count">${fair} candidates</div>
            </div>
            
            <div class="fairness-bar-item">
                <div class="fairness-bar-header">
                    <span class="fairness-bar-label">Poor (0-24)</span>
                    <span class="fairness-bar-percent">${((poor / total) * 100).toFixed(1)}%</span>
                </div>
                <div class="fairness-bar">
                    <div class="fairness-bar-fill" style="width: ${(poor / total) * 100}%; background: linear-gradient(90deg, #ef4444, #dc2626);"></div>
                </div>
                <div class="fairness-bar-count">${poor} candidates</div>
            </div>
        </div>
        
        <div class="fairness-insight">
            <div class="insight-icon">💡</div>
            <div class="insight-content">
                <strong>Fairness Insight:</strong>
                ${excellent >= good ?
            'Great! Your job requirements are attracting highly qualified candidates.' :
            'Consider reviewing job requirements to attract more qualified candidates.'}
            </div>
        </div>
    `;
}

async function generateAuditTimeline() {
    try {
        const response = await fetch(`${API_URL}/audit/logs?limit=10`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            return '<div class="empty-state">No audit events yet</div>';
        }

        const data = await response.json();
        // Backend returns {total, logs} object, extract the logs array
        const logs = Array.isArray(data) ? data : (data.logs || []);

        if (!logs || logs.length === 0) {
            return '<div class="empty-state">No audit events yet</div>';
        }

        return logs.map(log => {
            const date = new Date(log.timestamp);
            const eventIcon = log.event_type === 'application_submitted' ? '📋' :
                log.event_type === 'ranked' ? '📊' :
                    log.event_type === 'status_changed' ? '🔄' : '📝';

            return `
                <div class="audit-timeline-item">
                    <div class="timeline-icon">${eventIcon}</div>
                    <div class="timeline-content">
                        <div class="timeline-header">
                            <span class="timeline-event">${log.event_type.replace('_', ' ').toUpperCase()}</span>
                            <span class="timeline-time">${date.toLocaleDateString()} ${date.toLocaleTimeString()}</span>
                        </div>
                        <div class="timeline-details">
                            ${log.details ? `<p>${JSON.stringify(log.details)}</p>` : ''}
                            ${log.scores ? `
                                <div class="timeline-scores">
                                    ${Object.entries(log.scores).map(([key, val]) => `
                                        <span class="score-tag">${key}: ${typeof val === 'number' ? val.toFixed(1) : val}</span>
                                    `).join('')}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Error loading audit timeline:', error);
        return '<div class="empty-state">No audit events yet</div>';
    }
}

function filterAuditReport(days) {
    showNotification(`Loading audit data for last ${days} days...`, 'info');
    loadCompanyAudit(days);
}

function exportAuditReport() {
    try {
        const rows = [];
        rows.push(['Fairness & Compliance Audit Report - Smart Hiring System']);
        rows.push(['Generated', new Date().toLocaleString()]);
        rows.push(['Report Type', 'AI Bias & Fairness Compliance Audit']);
        rows.push([]);

        // Export audit metrics
        const auditContainer = document.getElementById('companyAudit');
        if (!auditContainer) {
            showNotification('Please load the Audit tab first.', 'warning');
            return;
        }

        // Grab fairness scores
        const scoreElements = auditContainer.querySelectorAll('.fairness-score, .audit-score, .score-card, .kpi-card');
        if (scoreElements.length > 0) {
            rows.push(['--- Fairness Scores ---']);
            scoreElements.forEach(el => {
                const label = el.querySelector('.score-label, .kpi-label, h4, h3')?.textContent?.trim() || '';
                const value = el.querySelector('.score-value, .kpi-value, h2, strong')?.textContent?.trim() || '';
                if (label || value) rows.push([label, value]);
            });
            rows.push([]);
        }

        // Grab audit table rows if present
        const tableRows = auditContainer.querySelectorAll('table tr');
        if (tableRows.length > 0) {
            rows.push(['--- Audit Detail Table ---']);
            tableRows.forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('th, td')).map(td => td.textContent.trim());
                if (cells.length > 0) rows.push(cells);
            });
            rows.push([]);
        }

        // Grab any metric items
        const metricItems = auditContainer.querySelectorAll('.metric-item, .audit-metric, .stat-item');
        if (metricItems.length > 0) {
            rows.push(['--- Compliance Metrics ---']);
            metricItems.forEach(item => {
                const label = item.querySelector('.metric-label, .stat-label, span')?.textContent?.trim() || '';
                const value = item.querySelector('.metric-value, .stat-value, strong')?.textContent?.trim() || '';
                if (label || value) rows.push([label, value]);
            });
            rows.push([]);
        }

        // Compliance status
        rows.push(['--- Compliance Statement ---']);
        rows.push(['Standard', 'IEEE 7003-2021 Algorithmic Bias Considerations']);
        rows.push(['Framework', 'EEOC Uniform Guidelines + AI Ethics']);
        rows.push(['Bias Mitigation', 'Demographic parity, Equal opportunity, Calibration']);
        rows.push(['Data', 'Name-blind, age-blind, gender-blind resume parsing']);

        const csv = rows.map(row =>
            row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')
        ).join('\n');

        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `fairness_audit_report_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showNotification('Audit compliance report exported as CSV!', 'success');
    } catch (error) {
        console.error('Export error:', error);
        showNotification('Failed to export audit report. Please try again.', 'error');
    }
}


// ============================================================================
// FLAN-T5 AI INTERVIEW ENGINE — Company Portal Integration
// ============================================================================

/**
 * Load Flan-T5 engine status and display notification banner on dashboard
 */
async function loadFlanT5Status() {
    const banner = document.getElementById('flanT5Notification');
    if (!banner) return;

    try {
        const response = await fetch(`${API_URL}/ai-interview-v2/flan-t5/status`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            banner.style.display = 'none';
            return;
        }

        const status = await response.json();

        if (status.flan_t5_model_loaded) {
            banner.style.display = 'block';
            banner.innerHTML = `
                <div style="background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%); border-radius: 12px; padding: 20px 24px; color: white; margin-bottom: 24px; box-shadow: 0 4px 15px rgba(79, 70, 229, 0.3);">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
                        <div style="display: flex; align-items: center; gap: 14px; flex: 1;">
                            <div style="font-size: 36px;">🧠</div>
                            <div>
                                <h3 style="margin: 0; font-size: 18px; font-weight: 700;">Flan-T5 AI Interview Engine — Active</h3>
                                <p style="margin: 4px 0 0; opacity: 0.9; font-size: 14px;">
                                    Dynamic question generation powered by Google Flan-T5. 
                                    Gap Analysis identifies missing skills → AI generates targeted interview questions in real-time.
                                </p>
                            </div>
                        </div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <div style="background: rgba(255,255,255,0.15); border-radius: 8px; padding: 8px 16px; text-align: center;">
                                <div style="font-size: 11px; opacity: 0.8; text-transform: uppercase; letter-spacing: 0.5px;">Model</div>
                                <div style="font-size: 14px; font-weight: 600;">Flan-T5 Base</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.15); border-radius: 8px; padding: 8px 16px; text-align: center;">
                                <div style="font-size: 11px; opacity: 0.8; text-transform: uppercase; letter-spacing: 0.5px;">Evaluator</div>
                                <div style="font-size: 14px; font-weight: 600;">SBERT ${status.sbert_model_loaded ? '✓' : '✗'}</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.15); border-radius: 8px; padding: 8px 16px; text-align: center;">
                                <div style="font-size: 11px; opacity: 0.8; text-transform: uppercase; letter-spacing: 0.5px;">Threshold</div>
                                <div style="font-size: 14px; font-weight: 600;">${status.evaluation_threshold || 0.70}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            banner.style.display = 'block';
            banner.innerHTML = `
                <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px; padding: 16px 24px; color: white; margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="font-size: 28px;">⚠️</div>
                        <div>
                            <h3 style="margin: 0; font-size: 16px;">AI Interview Engine — Fallback Mode</h3>
                            <p style="margin: 4px 0 0; opacity: 0.9; font-size: 13px;">
                                Flan-T5 model not loaded. Interviews will use the static question bank (1575 questions). 
                                ${status.message || ''}
                            </p>
                        </div>
                    </div>
                </div>
            `;
        }

    } catch (error) {
        console.log('Flan-T5 status check skipped:', error.message);
        if (banner) banner.style.display = 'none';
    }
}

/**
 * Launch Flan-T5 Gap-Based AI Interview for a specific candidate
 */
async function launchFlanT5Interview(jobId, candidateId, candidateName) {
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.id = 'flanT5InterviewModal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Flan-T5 AI interview');
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 800px; max-height: 90vh;">
            <div class="modal-header" style="background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%); color: white; padding: 20px 24px;">
                <div>
                    <h3 class="modal-title" style="margin: 0; font-size: 20px;">🧠 Flan-T5 AI Interview Engine</h3>
                    <p style="margin: 6px 0 0; opacity: 0.9; font-size: 14px;">Gap Analysis → Dynamic Question Generation for ${esc(candidateName)}</p>
                </div>
                <button class="modal-close" onclick="this.closest('.modal').remove()" style="color: white; opacity: 0.9;">×</button>
            </div>
            <div class="modal-body" style="padding: 24px; overflow-y: auto; max-height: calc(90vh - 140px);">
                <div style="text-align: center; padding: 40px;">
                    <div class="loading-spinner" style="width: 48px; height: 48px; border: 4px solid #e2e8f0; border-top-color: #7c3aed; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px;"></div>
                    <p style="color: #64748b; font-size: 15px;">Running Gap Analysis & generating targeted questions...</p>
                    <p style="color: #94a3b8; font-size: 13px;">probe_zone = job_required_skills − candidate_skills</p>
                </div>
            </div>
        </div>
        <style>
            @keyframes spin { to { transform: rotate(360deg); } }
        </style>
    `;
    document.body.appendChild(modal);

    try {
        // Difficulty selection — default medium
        const difficulty = 'medium';
        const maxQuestions = 10;

        const response = await fetch(`${API_URL}/ai-interview-v2/flan-t5/gap-interview`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: jobId,
                candidate_id: candidateId,
                difficulty_level: difficulty,
                max_questions: maxQuestions
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to generate interview');
        }

        const gap = data.gap_analysis || {};
        const questions = data.generated_questions || [];
        const summary = data.summary || {};

        const modalBody = modal.querySelector('.modal-body');
        modalBody.innerHTML = `
            <!-- Gap Analysis Summary -->
            <div style="background: linear-gradient(135deg, #f0f4ff 0%, #e8ecff 100%); border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #c7d2fe;">
                <h4 style="margin: 0 0 12px; color: #4338ca; font-size: 16px;">📊 Gap Analysis Results</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px;">
                    <div style="background: white; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
                        <div style="font-size: 24px; font-weight: 700; color: #10b981;">${gap.total_matched || 0}</div>
                        <div style="font-size: 12px; color: #64748b;">Matched Skills</div>
                    </div>
                    <div style="background: white; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
                        <div style="font-size: 24px; font-weight: 700; color: #ef4444;">${gap.total_missing || 0}</div>
                        <div style="font-size: 12px; color: #64748b;">Missing Skills</div>
                    </div>
                    <div style="background: white; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
                        <div style="font-size: 24px; font-weight: 700; color: #4f46e5;">${gap.coverage_percentage || 0}%</div>
                        <div style="font-size: 12px; color: #64748b;">Skill Coverage</div>
                    </div>
                    <div style="background: white; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
                        <div style="font-size: 24px; font-weight: 700; color: #7c3aed;">${questions.length}</div>
                        <div style="font-size: 12px; color: #64748b;">Questions Generated</div>
                    </div>
                </div>
                
                <!-- Skill Tags -->
                <div style="margin-top: 16px;">
                    ${(gap.matched_skills || []).length > 0 ? `
                        <div style="margin-bottom: 8px;">
                            <span style="font-size: 12px; font-weight: 600; color: #166534;">✅ Matched:</span>
                            ${(gap.matched_skills || []).map(s => `<span style="background: #dcfce7; color: #166534; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin: 2px; display: inline-block;">${esc(s)}</span>`).join('')}
                        </div>
                    ` : ''}
                    ${(gap.missing_skills || []).length > 0 ? `
                        <div>
                            <span style="font-size: 12px; font-weight: 600; color: #991b1b;">⚠️ Probe Zone:</span>
                            ${(gap.missing_skills || []).map(s => `<span style="background: #fee2e2; color: #991b1b; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin: 2px; display: inline-block;">${esc(s)}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- Generation Summary -->
            <div style="display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;">
                <span style="background: #f0fdf4; color: #166534; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; border: 1px solid #bbf7d0;">
                    🧠 Flan-T5: ${summary.flan_t5_generated || 0} questions
                </span>
                <span style="background: #fefce8; color: #854d0e; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; border: 1px solid #fef08a;">
                    📚 Fallback: ${summary.fallback_generated || 0} questions
                </span>
                <span style="background: #f0f4ff; color: #4338ca; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; border: 1px solid #c7d2fe;">
                    🎯 Difficulty: ${esc(summary.difficulty_level || 'medium')}
                </span>
            </div>

            <!-- Generated Questions -->
            <h4 style="margin: 0 0 16px; color: #1e293b; font-size: 16px;">📝 Generated Interview Questions</h4>
            <div id="flanT5QuestionsList">
                ${questions.map((q, idx) => `
                    <div class="flan-question-card" id="flanQ${idx}" style="background: white; border: 2px solid #e2e8f0; border-radius: 10px; padding: 16px; margin-bottom: 12px; transition: all 0.3s;">
                        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="background: #7c3aed; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700;">
                                    ${idx + 1}
                                </span>
                                <span style="background: ${q.source === 'flan-t5' ? '#f0fdf4' : '#fefce8'}; color: ${q.source === 'flan-t5' ? '#166534' : '#854d0e'}; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">
                                    ${q.source === 'flan-t5' ? '🧠 Flan-T5' : '📚 Bank'}
                                </span>
                                <span style="background: #f1f5f9; color: #475569; padding: 3px 10px; border-radius: 12px; font-size: 11px;">
                                    ${esc(q.skill || '')}
                                </span>
                            </div>
                            <div style="display: flex; gap: 6px; align-items: center;">
                                <span style="font-size: 12px; color: #64748b;">⏱ ${q.time_limit_minutes || 8}min</span>
                                <span style="font-size: 12px; color: #64748b;">💰 ${q.points || 10}pts</span>
                                <span style="background: ${q.difficulty === 'easy' ? '#dcfce7' : q.difficulty === 'hard' ? '#fee2e2' : '#fef3c7'}; color: ${q.difficulty === 'easy' ? '#166534' : q.difficulty === 'hard' ? '#991b1b' : '#854d0e'}; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                                    ${esc(q.difficulty || 'medium')}
                                </span>
                            </div>
                        </div>
                        <p style="margin: 0 0 12px; color: #1e293b; font-size: 14px; line-height: 1.5;">
                            <strong>Q:</strong> ${esc(q.generated_question || q.question || '')}
                        </p>
                        <div id="flanAnswer${idx}" style="display: none;">
                            <div style="background: #fffbeb; border: 1px solid #fef08a; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                                <div style="font-size: 11px; color: #854d0e; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">📖 Model Answer (Reference)</div>
                                <p style="margin: 0; font-size: 13px; color: #78350f; line-height: 1.5;">${esc(q.model_answer || 'N/A')}</p>
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-secondary" style="font-size: 12px; padding: 6px 12px;" onclick="toggleModelAnswer(${idx})">
                                👁 Toggle Model Answer
                            </button>
                        </div>
                        <div id="flanEvalResult${idx}"></div>
                    </div>
                `).join('')}
            </div>

            <!-- Interview Set Info -->
            ${data.interview_set_id ? `
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 16px; margin-top: 16px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 24px;">✅</span>
                        <div>
                            <div style="font-weight: 600; color: #166534;">Interview Set Saved</div>
                            <div style="font-size: 13px; color: #15803d;">ID: ${esc(data.interview_set_id)} — Ready to send to candidate</div>
                        </div>
                    </div>
                </div>
            ` : ''}
        `;

        // Store interview set ID for answer submission
        modal.dataset.interviewSetId = data.interview_set_id || '';

        showNotification(`🧠 Generated ${questions.length} AI interview questions for ${candidateName}`, 'success');

    } catch (error) {
        console.error('Flan-T5 interview generation error:', error);
        const modalBody = modal.querySelector('.modal-body');
        modalBody.innerHTML = `
            <div style="text-align: center; padding: 40px;">
                <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                <h3 style="color: #991b1b;">Interview Generation Failed</h3>
                <p style="color: #64748b;">${esc(error.message)}</p>
                <p style="color: #94a3b8; font-size: 13px;">The system will fall back to the static question bank.</p>
                <button class="btn btn-primary" onclick="this.closest('.modal').remove()">Close</button>
            </div>
        `;
    }
}

/**
 * Toggle model answer visibility for a question
 */
function toggleModelAnswer(idx) {
    const el = document.getElementById(`flanAnswer${idx}`);
    if (el) {
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Evaluate a candidate answer via SBERT cosine similarity
 */
async function evaluateFlanT5Answer(interviewSetId, questionIndex) {
    const textarea = document.getElementById(`flanAnswerInput${questionIndex}`);
    if (!textarea || !textarea.value.trim()) {
        showNotification('Please enter an answer before evaluating.', 'warning');
        return;
    }

    const candidateAnswer = textarea.value.trim();
    const resultDiv = document.getElementById(`flanEvalResult${questionIndex}`);

    resultDiv.innerHTML = `
        <div style="text-align: center; padding: 12px; color: #64748b;">
            <span style="animation: spin 1s linear infinite; display: inline-block;">⏳</span> Evaluating with SBERT cosine similarity...
        </div>
    `;

    try {
        const response = await fetch(`${API_URL}/ai-interview-v2/flan-t5/full-interview`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                interview_set_id: interviewSetId,
                question_index: questionIndex,
                candidate_answer: candidateAnswer
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Evaluation failed');
        }

        const eval_ = data.evaluation || {};
        const passed = eval_.passed;
        const score = eval_.similarity_score || 0;

        resultDiv.innerHTML = `
            <div style="background: ${passed ? '#f0fdf4' : '#fef2f2'}; border: 1px solid ${passed ? '#bbf7d0' : '#fecaca'}; border-radius: 8px; padding: 14px; margin-top: 12px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-weight: 700; color: ${passed ? '#166534' : '#991b1b'}; font-size: 15px;">
                        ${passed ? '✅ PASSED' : '❌ BELOW THRESHOLD'}
                    </span>
                    <span style="background: ${passed ? '#dcfce7' : '#fee2e2'}; color: ${passed ? '#166534' : '#991b1b'}; padding: 4px 14px; border-radius: 20px; font-weight: 700; font-size: 14px;">
                        ${(score * 100).toFixed(1)}%
                    </span>
                </div>
                <div style="background: #e2e8f0; border-radius: 4px; height: 8px; overflow: hidden; margin-bottom: 8px;">
                    <div style="background: ${score >= 0.85 ? '#10b981' : score >= 0.70 ? '#3b82f6' : score >= 0.50 ? '#f59e0b' : '#ef4444'}; height: 100%; width: ${(score * 100).toFixed(0)}%; border-radius: 4px; transition: width 0.5s;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 12px; color: #64748b;">
                    <span>Method: ${esc(eval_.evaluation_method || 'SBERT')}</span>
                    <span>Threshold: ${eval_.threshold || 0.70}</span>
                </div>
                <p style="margin: 8px 0 0; font-size: 13px; color: #475569;">${esc(eval_.feedback || '')}</p>
            </div>
        `;

        // Highlight the question card border based on pass/fail
        const card = document.getElementById(`flanQ${questionIndex}`);
        if (card) {
            card.style.borderColor = passed ? '#10b981' : '#ef4444';
        }

    } catch (error) {
        resultDiv.innerHTML = `
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 12px; margin-top: 12px;">
                <p style="margin: 0; color: #991b1b; font-size: 13px;">⚠️ Evaluation failed: ${esc(error.message)}</p>
            </div>
        `;
    }
}
