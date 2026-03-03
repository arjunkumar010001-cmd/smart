// Candidate Dashboard Module
// escapeHtml, esc, normalizeStatus, getStatusColor, getStatusIcon,
// getScoreClass, createModal, closeTopModal, anonymizeId — all from shared-utils.js

// ─── Global ESC-key & backdrop-click handler for candidate modals ───
(function () {
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const modals = document.querySelectorAll('.modal.show');
            if (modals.length > 0) {
                modals[modals.length - 1].remove();
                e.preventDefault();
            }
        }
    });
    document.addEventListener('click', function (e) {
        if (e.target.classList && e.target.classList.contains('modal') && e.target.classList.contains('show')) {
            e.target.remove();
        }
    });
})();

function loadCandidateDashboard() {
    const dashboard = document.getElementById('candidateDashboard');
    dashboard.innerHTML = `
        <nav class="navbar">
            <div class="navbar-brand">
                <svg width="32" height="32" viewBox="0 0 64 64">
                    <circle cx="32" cy="32" r="30" fill="#4F46E5"/>
                    <path d="M32 16L40 28H24L32 16Z" fill="white"/>
                    <rect x="22" y="30" width="20" height="18" rx="2" fill="white"/>
                </svg>
                <span>Candidate Portal</span>
            </div>
            <div class="navbar-menu">
                <button class="nav-link active" onclick="switchCandidateTab('browse', event)">🔍 Browse Jobs</button>
                <button class="nav-link" onclick="switchCandidateTab('applications', event)">📋 My Applications</button>
                <button class="nav-link" onclick="switchCandidateTab('interviews', event)">🎥 Interviews</button>
                <button class="nav-link" onclick="switchCandidateTab('assessments', event)">📝 Assessments</button>
                <button class="nav-link" onclick="switchCandidateTab('analytics', event)">📊 My Analytics</button>
                <button class="nav-link" onclick="switchCandidateTab('profile', event)">👤 Profile</button>
            </div>
            <div class="navbar-actions">
                <button class="theme-toggle-navbar" aria-label="Toggle Dark Mode" onclick="toggleTheme()">
                    <span class="theme-icon sun-icon">☀️</span>
                    <span class="theme-icon moon-icon" style="display:none;">🌙</span>
                </button>
                <span class="user-info">${currentUser.email}</span>
                <button class="btn btn-secondary" onclick="candidateLogout()">Logout</button>
            </div>
        </nav>
        <div class="main-content">
            <div id="candidateBrowse" class="tab-content active"></div>
            <div id="candidateApplications" class="tab-content"></div>
            <div id="candidateInterviews" class="tab-content"></div>
            <div id="candidateAssessments" class="tab-content"></div>
            <div id="candidateAnalytics" class="tab-content"></div>
            <div id="candidateProfile" class="tab-content"></div>
        </div>
    `;
    showPage('candidateDashboard');
    // Update theme icon state for the newly rendered toggle
    if (typeof updateThemeIcon === 'function') updateThemeIcon(document.body.getAttribute('data-theme') || 'light');
    loadCandidateBrowse();
}

function switchCandidateTab(tab, event) {
    // Remove active state from all nav links and content
    document.querySelectorAll('#candidateDashboard .nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('#candidateDashboard .tab-content').forEach(t => {
        t.classList.remove('active');
        t.style.display = 'none';
    });

    // Add active state to clicked nav link
    if (event && event.target) {
        event.target.classList.add('active');
    }

    // Show the selected tab content
    const tabContent = document.getElementById(`candidate${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
    if (tabContent) {
        tabContent.classList.add('active');
        tabContent.style.display = 'block';
    }

    // Load content based on tab with smooth transition
    switch (tab) {
        case 'browse': loadCandidateBrowse(); break;
        case 'applications': loadCandidateApplications(); break;
        case 'interviews': loadCandidateInterviews(); break;
        case 'assessments': loadCandidateAssessments(); break;
        case 'analytics': loadCandidateAnalytics(); break;
        case 'profile': loadCandidateProfile(); break;
    }

    // Scroll to top smoothly
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function loadCandidateBrowse() {
    const container = document.getElementById('candidateBrowse');
    container.innerHTML = '<div class="loading">Loading available jobs...</div>';

    try {
        const response = await fetch(`${API_URL}/jobs/list?status=open`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            throw new Error('Failed to load jobs');
        }

        const data = await response.json();
        const jobs = data.jobs || [];

        console.log(`Loaded ${jobs.length} jobs for candidates`);

        if (jobs.length === 0) {
            container.innerHTML = '<div class="empty-state">No jobs available at the moment. Check back soon!</div>';
            return;
        }

        container.innerHTML = `
            <div class="content-header">
                <h2>🔍 Browse Available Jobs</h2>
                <div class="search-bar">
                    <input type="text" id="jobSearch" placeholder="Search by title, skills, location..." onkeyup="filterJobs()">
                </div>
            </div>
            <div class="job-grid" id="jobsGrid">
                ${jobs.map(job => `
                    <div class="job-card" data-title="${escapeHtml(job.title.toLowerCase())}" data-skills="${escapeHtml((job.required_skills || []).join(' ').toLowerCase())}" data-location="${escapeHtml((job.location || '').toLowerCase())}">
                        <div class="job-header">
                            <div>
                                <h3 class="job-title">${escapeHtml(job.title)}</h3>
                                <p class="job-company">${escapeHtml(job.company_name || 'Company')}</p>
                            </div>
                            <span class="badge badge-success">Open</span>
                        </div>
                        <p class="job-description" style="white-space: pre-line;">${escapeHtml((job.description || '').substring(0, 200))}...</p>
                        <div class="job-meta">
                            <span>📍 ${escapeHtml(job.location || 'Remote')}</span>
                            <span>💼 ${escapeHtml(job.job_type || 'Full-time')}</span>
                            <span>📅 Posted ${job.posted_date ? new Date(job.posted_date).toLocaleDateString() : 'Recently'}</span>
                        </div>
                        <div class="job-tags">
                            ${(job.required_skills || []).slice(0, 5).map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('')}
                        </div>
                        <div style="display: flex; gap: 10px;">
                            <button class="btn btn-secondary" onclick="viewJobDetails('${job._id}')">View Details</button>
                            <button class="btn btn-primary" onclick="applyToJob('${job._id}')">Apply Now</button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (error) {
        console.error('Error loading jobs:', error);
        container.innerHTML = `
            <div class="empty-state">
                <p>❌ Failed to load jobs. Please try again later.</p>
                <button class="btn btn-primary" onclick="loadCandidateBrowse()">Retry</button>
            </div>
        `;
    }
}

function filterJobs() {
    const searchTerm = document.getElementById('jobSearch').value.toLowerCase();
    const cards = document.querySelectorAll('#jobsGrid .job-card');

    cards.forEach(card => {
        const title = card.dataset.title || '';
        const skills = card.dataset.skills || '';
        const location = card.dataset.location || '';

        if (title.includes(searchTerm) || skills.includes(searchTerm) || location.includes(searchTerm)) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });
}

async function viewJobDetails(jobId) {
    try {
        const response = await fetch(`${API_URL}/jobs/${jobId}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const job = await response.json();

        const modal = document.createElement('div');
        modal.className = 'modal show';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Job details');
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 700px;">
                <div class="modal-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; border-radius: 12px 12px 0 0;">
                    <h3 class="modal-title" style="margin: 0; font-size: 24px; font-weight: 700;">${job.title}</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()" style="color: white; opacity: 0.9;">×</button>
                </div>
                <div class="modal-body" style="padding: 32px;">
                    <!-- Job Info Cards -->
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 32px;">
                        <div style="background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%); padding: 16px; border-radius: 12px; border: 1px solid #e2e8f0;">
                            <div style="font-size: 24px; margin-bottom: 8px;">📍</div>
                            <div style="color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; font-weight: 600;">Location</div>
                            <div style="color: #1e293b; font-weight: 600; font-size: 14px;">${job.location}</div>
                        </div>
                        <div style="background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%); padding: 16px; border-radius: 12px; border: 1px solid #e2e8f0;">
                            <div style="font-size: 24px; margin-bottom: 8px;">💼</div>
                            <div style="color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; font-weight: 600;">Job Type</div>
                            <div style="color: #1e293b; font-weight: 600; font-size: 14px;">${job.job_type}</div>
                        </div>
                        <div style="background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%); padding: 16px; border-radius: 12px; border: 1px solid #e2e8f0;">
                            <div style="font-size: 24px; margin-bottom: 8px;">🏢</div>
                            <div style="color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; font-weight: 600;">Department</div>
                            <div style="color: #1e293b; font-weight: 600; font-size: 14px;">${job.department || 'Not specified'}</div>
                        </div>
                    </div>
                    
                    <!-- Description Section -->
                    <div style="margin-bottom: 32px; padding: 20px; background: #f8fafc; border-radius: 12px; border-left: 4px solid #667eea;">
                        <div style="color: #1e293b; font-weight: 700; font-size: 16px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 20px;">📋</span>
                            <span>Description</span>
                        </div>
                        <p style="color: #475569; line-height: 1.8; margin: 0; white-space: pre-line;">${escapeHtml((job.description || '').replace(/Requirements?:\s*/i, '').trim())}</p>
                    </div>
                    
                    <!-- Requirements Section -->
                    <div style="margin-bottom: 32px; padding: 20px; background: #f0fdf4; border-radius: 12px; border-left: 4px solid #10b981;">
                        <div style="color: #1e293b; font-weight: 700; font-size: 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 20px;">✅</span>
                            <span>Requirements</span>
                        </div>
                        <ul style="margin: 0; padding-left: 24px; color: #475569; line-height: 2;">
                            ${Array.isArray(job.requirements)
                ? job.requirements.map(r => `<li style="margin-bottom: 10px;">${escapeHtml(r)}</li>`).join('')
                : (job.requirements || '').split(/\n|\.(?=\s[A-Z])/).filter(r => r.trim() && !r.match(/^Requirements?:?\s*$/i)).map(r => `<li style="margin-bottom: 10px;">${escapeHtml(r.trim())}</li>`).join('')}
                        </ul>
                    </div>
                    
                    <!-- Required Skills Section -->
                    <div style="padding: 20px; background: #fef3f2; border-radius: 12px; border-left: 4px solid #f97316;">
                        <div style="color: #1e293b; font-weight: 700; font-size: 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 20px;">🎯</span>
                            <span>Required Skills</span>
                        </div>
                        <div class="job-tags" style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${(job.required_skills || []).map(s => `<span class="tag" style="background: white; border: 2px solid #f97316; color: #ea580c; font-weight: 600; padding: 8px 16px; border-radius: 8px;">${escapeHtml(s)}</span>`).join('')}
                        </div>
                    </div>
                </div>
                <div class="modal-footer" style="background: #f8fafc; padding: 20px 32px; border-radius: 0 0 12px 12px; display: flex; gap: 12px; justify-content: flex-end;">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()" style="padding: 12px 24px; border-radius: 8px; font-weight: 600;">Close</button>
                    ${(currentRole === 'candidate') ? `<button class="btn btn-primary" onclick="this.closest('.modal').remove(); applyToJob('${job._id}')" style="padding: 12px 32px; border-radius: 8px; font-weight: 600; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);">Apply Now</button>` : ''}
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    } catch (error) {
        alert('Failed to load job details');
    }
}

async function applyToJob(jobId) {
    if (!confirm('Apply to this job? Make sure you have completed required assessments and updated your profile.')) return;

    try {
        const response = await fetch(`${API_URL}/candidates/apply/${jobId}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        // Check content type before parsing as JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Server response:', text.substring(0, 200));
            throw new Error('Server returned invalid response. Please contact support.');
        }

        const data = await response.json();

        if (response.ok) {
            alert('✓ Application submitted successfully! Track it in "My Applications".');
            // Refresh the applications list
            setTimeout(() => {
                loadCandidateApplications();
            }, 1000);
        } else {
            throw new Error(data.message || data.error || 'Failed to apply');
        }
    } catch (error) {
        console.error('Application error:', error);
        alert('Failed to submit application: ' + error.message);
    }
}

async function loadCandidateApplications() {
    const container = document.getElementById('candidateApplications');
    container.innerHTML = '<div class="loading">Loading applications...</div>';

    try {
        const response = await fetch(`${API_URL}/candidates/applications`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const data = await response.json();
        const applications = data.applications || [];

        if (applications.length === 0) {
            container.innerHTML = `
                <div class="content-header">
                    <h2>📋 My Applications</h2>
                </div>
                <div class="empty-state">
                    No applications yet. Browse jobs and apply to get started!
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="content-header">
                <h2>📋 My Applications</h2>
            </div>
            <div class="job-grid">
                ${applications.map(app => `
                    <div class="job-card">
                        <div class="job-header">
                            <div>
                                <h3 class="job-title">${escapeHtml(app.job_title)}</h3>
                                <p class="job-company">${escapeHtml(app.company_name)}</p>
                            </div>
                            <span class="badge badge-${getStatusColorClass(app.status)}">${escapeHtml(app.status)}</span>
                        </div>
                        <div class="job-meta">
                            <span>📅 Applied: ${new Date(app.applied_at).toLocaleDateString()}</span>
                            <span>📍 ${escapeHtml(app.location)}</span>
                        </div>
                        ${app.interview_scheduled ? `
                            <div class="alert alert-info">
                                📅 Interview scheduled: ${new Date(app.interview_date).toLocaleString()}
                            </div>
                        ` : ''}
                        ${app.status === 'hired' ? buildOnboardingChecklist(app) : ''}
                    </div>
                `).join('')}
            </div>
        `;
    } catch (error) {
        container.innerHTML = '<div class="empty-state">Failed to load applications</div>';
    }
}

// getStatusColor is now provided by shared-utils.js
// Legacy wrapper kept for backward compat — candidate.js used string-based color classes
function getStatusColorClass(status) {
    const colors = {
        'pending': 'warning',
        'reviewing': 'info',
        'shortlisted': 'success',
        'interview': 'primary',
        'rejected': 'danger',
        'accepted': 'success'
    };
    return colors[status] || 'secondary';
}

function buildOnboardingChecklist(app) {
    const onboarding = app.onboarding || {};
    const steps = [
        { key: 'offer_accepted', label: 'Accept Offer Letter', icon: '📄', desc: 'Review and accept your offer letter' },
        { key: 'documents_uploaded', label: 'Upload Documents', icon: '📎', desc: 'ID proof, address proof, education certificates' },
        { key: 'profile_completed', label: 'Complete Profile', icon: '👤', desc: 'Fill in emergency contacts and bank details' },
        { key: 'nda_signed', label: 'Sign NDA / Agreements', icon: '✍️', desc: 'Non-disclosure and employment agreements' },
        { key: 'it_setup_requested', label: 'IT Setup Request', icon: '💻', desc: 'Request laptop, software access, and email' },
        { key: 'orientation_scheduled', label: 'Schedule Orientation', icon: '📅', desc: 'Pick a slot for your orientation session' }
    ];
    const completedCount = steps.filter(s => onboarding[s.key]).length;
    const progress = Math.round((completedCount / steps.length) * 100);

    return `
        <div style="margin-top: 12px; background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%); border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h4 style="margin: 0; color: #166534; font-size: 15px;">🎉 Onboarding Checklist</h4>
                <span style="font-size: 12px; color: #15803d; font-weight: 600;">${completedCount}/${steps.length} done</span>
            </div>
            <div style="background: #d1fae5; border-radius: 6px; height: 8px; margin-bottom: 12px; overflow: hidden;">
                <div style="background: #10b981; height: 100%; width: ${progress}%; border-radius: 6px; transition: width 0.3s;"></div>
            </div>
            ${steps.map((step, idx) => {
        const done = onboarding[step.key];
        return `
                <div style="display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; ${idx < steps.length - 1 ? 'border-bottom: 1px solid #d1fae5;' : ''}">
                    <span style="font-size: 18px; cursor: pointer;" onclick="toggleOnboardingStep('${app._id || app.id}', '${step.key}', ${!done})" title="${done ? 'Mark incomplete' : 'Mark complete'}">
                        ${done ? '✅' : '⬜'}
                    </span>
                    <div style="flex: 1;">
                        <span style="font-size: 13px; font-weight: 600; color: ${done ? '#6b7280' : '#1f2937'}; ${done ? 'text-decoration: line-through;' : ''}">${step.icon} ${step.label}</span>
                        <p style="margin: 2px 0 0; font-size: 12px; color: #6b7280;">${step.desc}</p>
                    </div>
                </div>`;
    }).join('')}
        </div>
    `;
}

async function toggleOnboardingStep(appId, stepKey, value) {
    try {
        const response = await fetch(`${API_URL}/candidates/applications/${appId}/onboarding`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ step: stepKey, completed: value })
        });
        if (response.ok) {
            loadCandidateApplications();
        } else {
            showNotification('Failed to update onboarding step', 'error');
        }
    } catch (err) {
        showNotification('Failed to update onboarding step: ' + err.message, 'error');
    }
}

async function loadCandidateInterviews() {
    const container = document.getElementById('candidateInterviews');
    container.innerHTML = '<div class="loading">Loading interviews...</div>';

    try {
        // Fetch video interview sessions for this candidate
        const userId = currentUser._id || currentUser.id;
        const response = await fetch(`${API_URL}/video-interview/candidate/${userId}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        let sessions = [];
        if (response.ok) {
            const data = await response.json();
            sessions = data.sessions || [];
        }

        // Also fetch from applications that have interview_scheduled
        const appResponse = await fetch(`${API_URL}/candidates/applications`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        let interviewApps = [];
        if (appResponse.ok) {
            const appData = await appResponse.json();
            interviewApps = (appData.applications || []).filter(app =>
                app.status === 'interviewed' || app.interview_scheduled || app.meeting_link
            );
        }

        if (sessions.length === 0 && interviewApps.length === 0) {
            container.innerHTML = `
                <div class="content-header">
                    <h2>🎥 My Interviews</h2>
                </div>
                <div class="empty-state">
                    No interviews scheduled yet. When a recruiter schedules an interview, it will appear here.
                </div>
            `;
            return;
        }

        let interviewCards = '';

        // Cards from video interview sessions
        sessions.forEach(s => {
            const status = s.status || 'scheduled';
            const statusColors = {
                'scheduled': '#4F46E5',
                'waiting': '#F59E0B',
                'in_progress': '#10B981',
                'completed': '#6B7280',
                'paused': '#F59E0B',
                'expired': '#EF4444',
                'cancelled': '#EF4444'
            };
            const statusColor = statusColors[status] || '#6B7280';
            const isJoinable = ['scheduled', 'waiting'].includes(status);
            const meetingLink = s.meeting_link || '';
            const scheduledTime = s.scheduled_time_display || (s.scheduled_time_utc ? new Date(s.scheduled_time_utc).toLocaleString() : 'ASAP');
            const interviewType = (s.interview_type || 'ai_automated').replace(/_/g, ' ');
            const typeIcon = s.interview_type === 'live' ? '👤' : s.interview_type === 'hybrid' ? '🔄' : '🤖';
            const typeBadgeColor = s.interview_type === 'live' ? '#3b82f6' : s.interview_type === 'hybrid' ? '#8b5cf6' : '#10b981';
            const hasRecording = s.recording_available || s.recording_path;
            const malpracticeCount = s.malpractice_events_count || 0;

            interviewCards += `
                <div class="job-card" style="border-left: 4px solid ${statusColor};">
                    <div class="job-header">
                        <div>
                            <h3 class="job-title">🎥 Video Interview</h3>
                            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px;">
                                <span style="background: ${typeBadgeColor}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">
                                    ${typeIcon} ${escapeHtml(interviewType)}
                                </span>
                                ${hasRecording ? '<span style="background: #fee2e2; color: #991b1b; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">🔴 Recorded</span>' : ''}
                                ${malpracticeCount > 0 ? `<span style="background: #fef3c7; color: #92400e; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">⚠️ ${malpracticeCount} flags</span>` : ''}
                            </div>
                        </div>
                        <span class="badge" style="background: ${statusColor}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px;">
                            ${escapeHtml(status.replace(/_/g, ' ').toUpperCase())}
                        </span>
                    </div>
                    <div class="job-meta">
                        <span>📅 ${escapeHtml(scheduledTime)}</span>
                        <span>⏱ ${s.duration_minutes || 90} min</span>
                        ${s.questions_count ? `<span>❓ ${s.questions_count} questions</span>` : ''}
                    </div>
                    ${s.evaluation_score !== undefined && status === 'completed' ? `
                        <div style="margin-top: 12px; background: ${s.evaluation_score >= 70 ? '#f0fdf4' : s.evaluation_score >= 50 ? '#fefce8' : '#fef2f2'}; border-radius: 8px; padding: 12px; border-left: 3px solid ${s.evaluation_score >= 70 ? '#10b981' : s.evaluation_score >= 50 ? '#f59e0b' : '#ef4444'};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-weight: 600; color: #1e293b;">Interview Score</span>
                                <span style="font-size: 18px; font-weight: 700; color: ${s.evaluation_score >= 70 ? '#10b981' : s.evaluation_score >= 50 ? '#f59e0b' : '#ef4444'};">${s.evaluation_score}%</span>
                            </div>
                        </div>
                    ` : ''}
                    ${isJoinable ? `
                        <div style="margin-top: 12px;">
                            <a href="${escapeHtml(meetingLink)}" target="_blank" 
                               class="btn btn-primary" style="display: inline-block; text-decoration: none; padding: 10px 24px; font-weight: 600;">
                                🚀 Join Interview
                            </a>
                        </div>
                    ` : ''}
                    ${status === 'in_progress' ? `
                        <div style="margin-top: 12px;">
                            <a href="${escapeHtml(meetingLink)}" target="_blank" 
                               class="btn btn-primary" style="display: inline-block; text-decoration: none; padding: 10px 24px; font-weight: 600; background: linear-gradient(135deg, #10b981, #059669);">
                                ▶️ Resume Interview
                            </a>
                        </div>
                    ` : ''}
                    ${status === 'completed' ? `
                        <div style="margin-top: 8px; color: #6B7280; font-size: 13px;">
                            ✅ Interview completed ${s.completed_at ? 'on ' + new Date(s.completed_at).toLocaleString() : ''}
                        </div>
                    ` : ''}
                </div>
            `;
        });

        // Cards from applications with meeting links (fallback)
        interviewApps.forEach(app => {
            if (app.meeting_link && !sessions.some(s => s.meeting_link === app.meeting_link)) {
                interviewCards += `
                    <div class="job-card" style="border-left: 4px solid #4F46E5;">
                        <div class="job-header">
                            <div>
                                <h3 class="job-title">${escapeHtml(app.job_title || 'Interview')}</h3>
                                <p class="job-company">${escapeHtml(app.company_name || '')}</p>
                            </div>
                            <span class="badge badge-primary">INTERVIEW</span>
                        </div>
                        <div class="job-meta">
                            ${app.interview_date ? `<span>📅 ${new Date(app.interview_date).toLocaleString()}</span>` : ''}
                        </div>
                        <div style="margin-top: 12px;">
                            <a href="${escapeHtml(app.meeting_link)}" target="_blank"
                               class="btn btn-primary" style="display: inline-block; text-decoration: none; padding: 10px 24px; font-weight: 600;">
                                🚀 Join Interview
                            </a>
                        </div>
                    </div>
                `;
            }
        });

        container.innerHTML = `
            <div class="content-header">
                <h2>🎥 My Interviews</h2>
            </div>
            <div class="job-grid">
                ${interviewCards}
            </div>
        `;
    } catch (error) {
        console.error('Failed to load interviews:', error);
        container.innerHTML = '<div class="empty-state">Failed to load interviews</div>';
    }
}

async function loadCandidateAssessments() {
    const container = document.getElementById('candidateAssessments');
    container.innerHTML = '<div class="loading">Loading assessments...</div>';

    try {
        const response = await fetch(`${API_URL}/assessments/quizzes`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            throw new Error('Failed to load assessments');
        }

        const data = await response.json();
        const quizzes = data.quizzes || [];

        // Get quiz attempts to show completed quizzes
        const attemptsResponse = await fetch(`${API_URL}/assessments/my-attempts`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const attemptsData = attemptsResponse.ok ? await attemptsResponse.json() : { attempts: [] };
        const attempts = attemptsData.attempts || [];

        // Calculate stats
        const completedCount = attempts.filter(a => a.status === 'completed').length;
        const avgScore = completedCount > 0 ?
            Math.round(attempts.filter(a => a.status === 'completed').reduce((sum, a) => sum + (a.score || 0), 0) / completedCount) :
            0;

        container.innerHTML = `
            <div class="content-header">
                <h2>📝 Skill Assessments</h2>
            </div>
            <div class="card">
                <h3>Why Take Assessments?</h3>
                <p>Complete skill assessments to showcase your capabilities. Higher scores increase your chances of getting matched with relevant job opportunities!</p>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-icon">✅</div>
                        <div class="stat-content">
                            <div class="stat-label">Completed</div>
                            <div class="stat-value">${completedCount}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">📊</div>
                        <div class="stat-content">
                            <div class="stat-label">Average Score</div>
                            <div class="stat-value">${completedCount > 0 ? avgScore + '%' : '-'}</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">📝</div>
                        <div class="stat-content">
                            <div class="stat-label">Available</div>
                            <div class="stat-value">${quizzes.length}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            ${quizzes.length > 0 ? `
                <div class="card">
                    <h3>📋 Available Assessments</h3>
                    <div class="jobs-grid">
                        ${quizzes.map(quiz => {
            const attempt = attempts.find(a => a.quiz_id === quiz._id);
            const isCompleted = attempt && attempt.status === 'completed';
            const score = isCompleted ? attempt.score : null;

            return `
                                <div class="job-card">
                                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                                        <h3 style="margin: 0;">${quiz.title}</h3>
                                        ${isCompleted ? `<span class="tag" style="background: #10b981; color: white;">✓ Completed</span>` :
                    `<span class="tag" style="background: #3b82f6; color: white;">Available</span>`}
                                    </div>
                                    <p style="color: #64748b; margin-bottom: 16px;">${quiz.description || 'Test your skills'}</p>
                                    <div style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;">
                                        <span>⏱️ ${quiz.duration_minutes} minutes</span>
                                        <span>❓ ${quiz.questions?.length || 0} questions</span>
                                        <span>🎯 ${quiz.passing_score || 70}% to pass</span>
                                    </div>
                                    ${isCompleted ? `
                                        <div class="alert ${score >= (quiz.passing_score || 70) ? 'alert-success' : 'alert-warning'}" style="margin-bottom: 16px;">
                                            ${score >= (quiz.passing_score || 70) ? '✓' : '⚠️'} Your Score: ${score}% 
                                            ${score >= (quiz.passing_score || 70) ? '(Passed)' : '(Did not pass)'}
                                        </div>
                                    ` : ''}
                                    <button class="btn ${isCompleted ? 'btn-secondary' : 'btn-primary'}" 
                                            onclick="${isCompleted ? `viewQuizResults('${quiz._id}')` : `startQuiz('${quiz._id}')`}">
                                        ${isCompleted ? '📊 View Results' : '▶️ Start Assessment'}
                                    </button>
                                </div>
                            `;
        }).join('')}
                    </div>
                </div>
            ` : `
                <div class="card">
                    <div class="empty-state">
                        <div style="font-size: 64px; margin-bottom: 16px;">📝</div>
                        <h3>No Assessments Available Yet</h3>
                        <p>Assessments become available when you apply to jobs that require skill testing.</p>
                        <p style="color: #64748b;">Apply to jobs with assessment requirements to see them here!</p>
                    </div>
                </div>
            `}
        `;

        // ── Job-Required Assigned Sessions (Bug #1 fix) ──
        try {
            const sessionsResp = await fetch(`${API_URL}/smart-assessments/my-sessions`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (sessionsResp.ok) {
                const sessionsData = await sessionsResp.json();
                const sessions = (sessionsData.sessions || []).filter(s => s.application_id);
                if (sessions.length > 0) {
                    container.innerHTML += `
                        <div class="card" style="margin-top:24px;border:2px solid #f59e0b;background:linear-gradient(135deg,#fffbeb,#fff);">
                            <h3>📋 Job-Required Assessments</h3>
                            <p style="color:#64748b;margin-bottom:16px;">Complete these assessments to advance your job applications.</p>
                            <div class="jobs-grid">
                                ${sessions.map(session => {
                        const expiryDate = session.expires_at ? new Date(session.expires_at) : null;
                        const daysLeft = expiryDate ? Math.ceil((expiryDate - Date.now()) / (1000 * 60 * 60 * 24)) : null;
                        const isExpired = daysLeft !== null && daysLeft < 0;
                        const isCompleted = session.status === 'completed';
                        const statusBadge = isCompleted
                            ? '<span class="tag" style="background:#10b981;color:white;">Completed</span>'
                            : isExpired
                                ? '<span class="tag" style="background:#ef4444;color:white;">Expired</span>'
                                : '<span class="tag" style="background:#f59e0b;color:white;">Required</span>';

                        return `
                                        <div class="job-card" style="border-left:4px solid ${isExpired ? '#ef4444' : isCompleted ? '#10b981' : '#f59e0b'};">
                                            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">
                                                <h3 style="margin:0;">${escapeHtml ? escapeHtml(session.config_title || 'Assessment') : (session.config_title || 'Assessment')}</h3>
                                                ${statusBadge}
                                            </div>
                                            <p style="color:#64748b;font-size:13px;margin-bottom:8px;">
                                                For: <strong>${escapeHtml ? escapeHtml(session.job_title || 'Job Application') : (session.job_title || 'Job Application')}</strong>
                                            </p>
                                            <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:13px;margin-bottom:12px;">
                                                <span>🔄 ${session.attempts_remaining || 0} attempts left</span>
                                                ${session.duration_minutes ? '<span>⏱️ ' + session.duration_minutes + ' min</span>' : ''}
                                                ${session.question_count ? '<span>📝 ' + session.question_count + ' questions</span>' : ''}
                                            </div>
                                            ${expiryDate ? `
                                                <div style="font-size:12px;padding:6px 10px;border-radius:6px;margin-bottom:12px;${isExpired ? 'background:#fef2f2;color:#dc2626;' : 'background:#fffbeb;color:#d97706;'}">
                                                    ${isExpired
                                    ? 'Expired on ' + expiryDate.toLocaleDateString()
                                    : daysLeft + ' day' + (daysLeft !== 1 ? 's' : '') + ' left (expires ' + expiryDate.toLocaleDateString() + ')'
                                }
                                                </div>
                                            ` : ''}
                                            ${isCompleted ? `
                                                <div class="alert alert-success" style="margin-bottom:12px;">
                                                    Score: ${session.final_percentage || 0}% ${session.passed ? '(Passed)' : '(Did not pass)'}
                                                </div>
                                            ` : ''}
                                            <button class="btn btn-primary" onclick="window.location.href='smart-assessment.html?session=${session._id}'"
                                                ${isExpired || isCompleted ? 'disabled' : ''}>
                                                ${isCompleted ? 'View Results' : isExpired ? 'Expired' : 'Start Assessment'}
                                            </button>
                                        </div>
                                    `;
                    }).join('')}
                            </div>
                        </div>
                    `;
                }
            }
        } catch (sessErr) {
            console.warn('Job-required sessions not available:', sessErr);
        }

        // ── AI-Powered Smart Assessments Section ──
        try {
            const smartResp = await fetch(`${API_URL}/smart-assessments/available`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (smartResp.ok) {
                const smartData = await smartResp.json();
                const smartConfigs = smartData.configs || [];
                if (smartConfigs.length > 0) {
                    container.innerHTML += `
                        <div class="card" style="margin-top:24px;border:2px solid #818cf8;background:linear-gradient(135deg,#eef2ff,#fff);">
                            <h3>🤖 AI-Powered Smart Assessments</h3>
                            <p style="color:#64748b;margin-bottom:16px;">Advanced assessments with AI-generated questions, live code execution, and intelligent scoring.</p>
                            <div class="jobs-grid">
                                ${smartConfigs.map(cfg => `
                                    <div class="job-card" style="border-left:4px solid #6366f1;">
                                        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">
                                            <h3 style="margin:0;">${escapeHTML ? escapeHTML(cfg.title) : cfg.title}</h3>
                                            <span class="tag" style="background:#6366f1;color:white;">AI Assessment</span>
                                        </div>
                                        <p style="color:#64748b;font-size:13px;margin-bottom:12px;">${escapeHTML ? escapeHTML(cfg.description || cfg.job_role) : (cfg.description || cfg.job_role)}</p>
                                        <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:13px;margin-bottom:12px;">
                                            <span>📝 ${cfg.total_questions} questions</span>
                                            <span>⏱️ ${cfg.duration_minutes} min</span>
                                            <span>🎯 ${cfg.passing_score}% to pass</span>
                                        </div>
                                        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
                                            ${(cfg.question_types || []).map(t => `<span style="padding:2px 8px;background:#f1f5f9;border-radius:4px;font-size:11px;">${t}</span>`).join('')}
                                        </div>
                                        <button class="btn btn-primary" onclick="window.location.href='smart-assessment.html?config=${cfg._id}'">
                                            🚀 Start AI Assessment
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }
            }
        } catch (smartErr) {
            console.warn('Smart assessments not available:', smartErr);
        }

    } catch (error) {
        console.error('Failed to load assessments:', error);
        container.innerHTML = `
            <div class="content-header">
                <h2>📝 Skill Assessments</h2>
            </div>
            <div class="card">
                <div class="alert alert-error">
                    Failed to load assessments. Please try again later.
                </div>
            </div>
        `;
    }
}

async function startQuiz(quizId) {
    if (!confirm('Are you ready to start this assessment? The timer will begin immediately.')) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/assessments/quizzes/${quizId}/start`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to start quiz');
        }

        const data = await response.json();
        const attemptId = data.attempt_id || (data.attempt && data.attempt._id);
        const questions = data.questions || [];
        const quizInfo = data.quiz || {};

        if (!questions.length) {
            showNotification('No questions found for this quiz', 'warning');
            return;
        }

        // Render inline quiz-taking interface
        const container = document.getElementById('candidateAssessments');
        let currentQ = 0;
        const answers = {};
        const startTime = Date.now();

        function renderQuestion() {
            const q = questions[currentQ];
            const progress = Math.round(((currentQ + 1) / questions.length) * 100);
            container.innerHTML = `
                <div class="content-header">
                    <h2>📝 ${escapeHtml(quizInfo.title || 'Assessment')}</h2>
                    <button class="btn btn-secondary" onclick="if(confirm('Are you sure? Your progress will be lost.')) loadCandidateAssessments();">✕ Exit</button>
                </div>
                <div class="card" style="max-width: 800px; margin: 0 auto;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <span style="font-weight: 600; color: #6366f1;">Question ${currentQ + 1} of ${questions.length}</span>
                        <span style="font-size: 13px; color: #64748b;">⏱️ ${quizInfo.duration || 30} min limit</span>
                    </div>
                    <div style="background: #e2e8f0; border-radius: 6px; height: 6px; margin-bottom: 20px; overflow: hidden;">
                        <div style="background: #6366f1; height: 100%; width: ${progress}%; transition: width 0.3s;"></div>
                    </div>
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 16px;">${escapeHtml(q.question_text)}</div>
                    ${q.question_type === 'multiple_choice' || q.question_type === 'true_false' ? `
                        <div style="display: flex; flex-direction: column; gap: 8px;">
                            ${(q.options || []).map((opt, idx) => `
                                <label style="display: flex; align-items: center; gap: 10px; padding: 12px 16px; border: 2px solid ${answers[q._id] === opt ? '#6366f1' : '#e2e8f0'}; border-radius: 8px; cursor: pointer; transition: all 0.2s; background: ${answers[q._id] === opt ? '#eef2ff' : 'white'};" 
                                       onclick="document.querySelectorAll('.quiz-option').forEach(e=>e.style.borderColor='#e2e8f0');this.style.borderColor='#6366f1';this.style.background='#eef2ff';">
                                    <input type="radio" name="quiz_answer" value="${escapeHtml(opt)}" class="quiz-option" ${answers[q._id] === opt ? 'checked' : ''} onchange="window._quizSelectAnswer('${q._id}', '${escapeHtml(opt)}')" style="display:none;">
                                    <span style="width: 24px; height: 24px; border-radius: 50%; border: 2px solid ${answers[q._id] === opt ? '#6366f1' : '#cbd5e1'}; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #6366f1; font-weight: bold; flex-shrink: 0; background: ${answers[q._id] === opt ? '#6366f1' : 'white'}; color: ${answers[q._id] === opt ? 'white' : '#6366f1'};">${String.fromCharCode(65 + idx)}</span>
                                    <span>${escapeHtml(opt)}</span>
                                </label>
                            `).join('')}
                        </div>
                    ` : `
                        <textarea id="shortAnswer" rows="4" class="form-control" placeholder="Type your answer here..." style="width: 100%; resize: vertical;">${answers[q._id] || ''}</textarea>
                    `}
                    <div style="display: flex; justify-content: space-between; margin-top: 24px;">
                        <button class="btn btn-secondary" ${currentQ === 0 ? 'disabled' : ''} onclick="window._quizPrev()">← Previous</button>
                        ${currentQ < questions.length - 1 ?
                    `<button class="btn btn-primary" onclick="window._quizNext()">Next →</button>` :
                    `<button class="btn btn-primary" style="background: #10b981;" onclick="window._quizSubmit()">✓ Submit Assessment</button>`
                }
                    </div>
                </div>
            `;
        }

        window._quizSelectAnswer = (qId, answer) => { answers[qId] = answer; };
        window._quizPrev = () => { if (currentQ > 0) { currentQ--; renderQuestion(); } };
        window._quizNext = () => {
            const q = questions[currentQ];
            if (q.question_type === 'short_answer') {
                const val = document.getElementById('shortAnswer')?.value;
                if (val) answers[q._id] = val;
            }
            if (currentQ < questions.length - 1) { currentQ++; renderQuestion(); }
        };
        window._quizSubmit = async () => {
            const q = questions[currentQ];
            if (q.question_type === 'short_answer') {
                const val = document.getElementById('shortAnswer')?.value;
                if (val) answers[q._id] = val;
            }
            const answeredCount = Object.keys(answers).length;
            if (answeredCount < questions.length && !confirm(`You've answered ${answeredCount}/${questions.length} questions. Submit anyway?`)) return;

            try {
                const submitResp = await fetch(`${API_URL}/assessments/attempts/${attemptId}/submit`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ answers, time_spent: Math.round((Date.now() - startTime) / 1000) })
                });
                if (submitResp.ok) {
                    const result = await submitResp.json();
                    showNotification(`Assessment submitted! Score: ${result.percentage}% ${result.passed ? '✓ Passed!' : ''}`, result.passed ? 'success' : 'warning');
                } else {
                    showNotification('Failed to submit assessment', 'error');
                }
            } catch (err) {
                showNotification('Submit error: ' + err.message, 'error');
            }
            loadCandidateAssessments();
        };

        renderQuestion();
    } catch (error) {
        console.error('Start quiz error:', error);
        showNotification('Failed to start assessment: ' + error.message, 'error');
    }
}

async function viewQuizResults(quizId) {
    try {
        const attemptsResp = await fetch(`${API_URL}/assessments/my-attempts`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!attemptsResp.ok) { showNotification('Failed to load results', 'error'); return; }
        const attData = await attemptsResp.json();
        const attempt = (attData.attempts || []).find(a => a.quiz_id === quizId && a.status === 'completed');
        if (!attempt) { showNotification('No completed attempt found', 'warning'); return; }

        const modal = document.createElement('div');
        modal.className = 'modal show';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Assessment results');
        const score = attempt.percentage || 0;
        const passed = attempt.passed;
        const correct = attempt.correct_count || 0;
        const incorrect = attempt.incorrect_count || 0;
        const unanswered = attempt.unanswered_count || 0;
        const total = correct + incorrect + unanswered;

        modal.innerHTML = `
            <div class="modal-content" style="max-width: 550px;">
                <div class="modal-header">
                    <h3 class="modal-title">📊 Assessment Results</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    <div style="text-align: center; padding: 20px 0;">
                        <div style="font-size: 56px; font-weight: 800; color: ${passed ? '#10b981' : '#ef4444'};">${Math.round(score)}%</div>
                        <div style="font-size: 18px; font-weight: 600; color: ${passed ? '#166534' : '#991b1b'}; margin-top: 4px;">
                            ${passed ? '✓ Passed' : '✗ Did Not Pass'}
                        </div>
                        <div style="font-size: 13px; color: #64748b; margin-top: 4px;">
                            ${attempt.quiz_title || 'Assessment'}
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin: 16px 0;">
                        <div style="text-align: center; padding: 12px; background: #f0fdf4; border-radius: 8px;">
                            <div style="font-size: 20px; font-weight: 700; color: #166534;">${correct}</div>
                            <div style="font-size: 12px; color: #15803d;">Correct</div>
                        </div>
                        <div style="text-align: center; padding: 12px; background: #fef2f2; border-radius: 8px;">
                            <div style="font-size: 20px; font-weight: 700; color: #991b1b;">${incorrect}</div>
                            <div style="font-size: 12px; color: #b91c1c;">Incorrect</div>
                        </div>
                        <div style="text-align: center; padding: 12px; background: #fefce8; border-radius: 8px;">
                            <div style="font-size: 20px; font-weight: 700; color: #854d0e;">${unanswered}</div>
                            <div style="font-size: 12px; color: #a16207;">Skipped</div>
                        </div>
                    </div>
                    ${attempt.completed_at ? `<p style="text-align: center; font-size: 12px; color: #94a3b8;">Completed: ${new Date(attempt.completed_at).toLocaleString()}</p>` : ''}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    } catch (err) {
        showNotification('Failed to load results: ' + err.message, 'error');
    }
}

async function loadCandidateProfile() {
    const container = document.getElementById('candidateProfile');
    container.innerHTML = '<div class="loading">Loading profile...</div>';

    try {
        const response = await fetch(`${API_URL}/candidates/profile`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!response.ok) {
            throw new Error('Profile not found');
        }

        const profile = await response.json();

        // Safely get profile data with proper defaults
        const firstName = profile.first_name || currentUser.full_name?.split(' ')[0] || 'User';
        const lastName = profile.last_name || currentUser.full_name?.split(' ').slice(1).join(' ') || '';
        const email = profile.email || currentUser.email || 'Not provided';
        const phone = profile.phone || 'Not provided';
        const skills = profile.skills || [];
        const experience = profile.experience_years || profile.experience || 0;
        const education = profile.education || 'Not provided';
        const bio = profile.bio || '';
        const location = profile.location || '';
        const linkedin = profile.linkedin || '';
        const portfolio = profile.portfolio || '';
        const resumeUploaded = profile.resume_uploaded || profile.resume_file || false;

        container.innerHTML = `
            <div class="content-header">
                <h2>👤 My Profile</h2>
                <button class="btn btn-primary" onclick="editProfile()">✏️ Edit Profile</button>
            </div>
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 24px;">
                    <div>
                        <h3>${firstName} ${lastName}</h3>
                        <p>📧 ${email}</p>
                        <p>📞 ${phone}</p>
                        ${location ? `<p>📍 ${location}</p>` : ''}
                    </div>
                    <div style="text-align: right;">
                        ${linkedin ? `<a href="${linkedin}" target="_blank" class="btn btn-secondary" style="margin-bottom: 8px; display: inline-block;">🔗 LinkedIn</a><br>` : ''}
                        ${portfolio ? `<a href="${portfolio}" target="_blank" class="btn btn-secondary" style="display: inline-block;">🌐 Portfolio</a>` : ''}
                    </div>
                </div>
                
                ${bio ? `
                    <h4>About Me</h4>
                    <p style="color: #4a5568; line-height: 1.6; margin-bottom: 24px;">${bio}</p>
                ` : ''}
                
                <h4>Skills</h4>
                <div class="job-tags" style="margin-bottom: 24px;">
                    ${skills.length > 0 ?
                skills.map(s => `<span class="tag">${s}</span>`).join('') :
                '<p class="text-muted">No skills added</p>'
            }
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 24px; margin-bottom: 24px;">
                    <div>
                        <h4>Experience</h4>
                        <p>${experience} years</p>
                    </div>
                    <div>
                        <h4>Education</h4>
                        <p>${education}</p>
                    </div>
                </div>
                
                <h4>Resume</h4>
                ${resumeUploaded ?
                `<div class="alert alert-success">✓ Resume uploaded successfully</div>
                     <button class="btn btn-secondary" onclick="uploadResume()">📤 Upload New Resume</button>` :
                `<div class="alert alert-warning">⚠️ No resume uploaded. Upload your resume to apply to jobs.</div>
                     <button class="btn btn-primary" onclick="uploadResume()">📤 Upload Resume</button>`
            }
            </div>
        `;
    } catch (error) {
        console.error('Profile load error:', error);
        // Create default profile view with current user data
        const firstName = currentUser.full_name?.split(' ')[0] || 'User';
        const lastName = currentUser.full_name?.split(' ').slice(1).join(' ') || '';

        container.innerHTML = `
            <div class="content-header">
                <h2>👤 My Profile</h2>
            </div>
            <div class="card">
                <h3>${firstName} ${lastName}</h3>
                <p>📧 ${currentUser.email || 'undefined'}</p>
                <p>📞 Not provided</p>
                
                <h4>Skills</h4>
                <p class="text-muted">No skills added</p>
                
                <h4>Experience</h4>
                <p>0 years</p>
                
                <h4>Education</h4>
                <p>Not provided</p>
                
                <h4>Resume</h4>
                <div class="alert alert-warning">⚠️ Complete your profile to improve your job matches!</div>
                <button class="btn btn-primary" onclick="uploadResume()">📤 Upload Resume</button>
            </div>
        `;
    }
}

async function editProfile() {
    // Fetch fresh profile data from API instead of scraping DOM
    let profile = {};
    try {
        const response = await fetch(`${API_URL}/candidates/profile`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (response.ok) {
            profile = await response.json();
        }
    } catch (error) {
        console.error('Failed to fetch profile for editing:', error);
    }

    // Extract data with proper fallbacks
    const firstName = profile.first_name || currentUser.full_name?.split(' ')[0] || '';
    const lastName = profile.last_name || currentUser.full_name?.split(' ').slice(1).join(' ') || '';
    const currentEmail = profile.email || currentUser.email || '';
    const currentPhone = profile.phone || '';
    const currentSkills = (profile.skills || []).join(', ');
    const currentExperience = profile.experience_years || profile.experience || 0;
    const currentEducation = profile.education || '';
    const currentLocation = profile.location || '';
    const currentBio = profile.bio || '';
    const currentLinkedin = profile.linkedin || '';
    const currentPortfolio = profile.portfolio || '';

    // Create edit profile modal
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Edit profile');
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">✏️ Edit Profile</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <form id="editProfileForm" onsubmit="submitProfileEdit(event)">
                <div class="modal-body">
                    <div class="form-row">
                        <div class="form-group">
                            <label>First Name *</label>
                            <input type="text" name="firstName" value="${escapeHtml(firstName)}" required placeholder="Enter first name">
                        </div>
                        <div class="form-group">
                            <label>Last Name *</label>
                            <input type="text" name="lastName" value="${escapeHtml(lastName)}" required placeholder="Enter last name">
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Email *</label>
                        <input type="email" name="email" value="${escapeHtml(currentEmail)}" required disabled>
                        <small style="color: #718096;">Email cannot be changed</small>
                    </div>
                    
                    <div class="form-group">
                        <label>Phone Number</label>
                        <div style="display: flex; gap: 8px;">
                            <select name="country_code" style="width: 140px;">
                                <option value="+1">🇺🇸 +1 (US)</option>
                                <option value="+44">🇬🇧 +44 (UK)</option>
                                <option value="+91" selected>🇮🇳 +91 (India)</option>
                                <option value="+61">🇦🇺 +61 (Australia)</option>
                                <option value="+81">🇯🇵 +81 (Japan)</option>
                                <option value="+86">🇨🇳 +86 (China)</option>
                                <option value="+49">🇩🇪 +49 (Germany)</option>
                                <option value="+33">🇫🇷 +33 (France)</option>
                                <option value="+39">🇮🇹 +39 (Italy)</option>
                                <option value="+34">🇪🇸 +34 (Spain)</option>
                                <option value="+7">🇷🇺 +7 (Russia)</option>
                                <option value="+55">🇧🇷 +55 (Brazil)</option>
                                <option value="+52">🇲🇽 +52 (Mexico)</option>
                                <option value="+27">🇿🇦 +27 (S. Africa)</option>
                                <option value="+82">🇰🇷 +82 (S. Korea)</option>
                                <option value="+65">🇸🇬 +65 (Singapore)</option>
                            </select>
                            <input type="tel" name="phone" value="${escapeHtml(currentPhone)}" placeholder="1234567890" style="flex: 1;">
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Skills (comma-separated)</label>
                        <input type="text" name="skills" value="${escapeHtml(currentSkills)}" 
                               placeholder="JavaScript, Python, React, Node.js">
                        <small style="color: #718096;">Separate skills with commas</small>
                    </div>
                    
                    <div class="form-row">
                        <div class="form-group">
                            <label>Years of Experience</label>
                            <input type="number" name="experience" value="${currentExperience}" 
                                   min="0" max="50" step="0.5" placeholder="0">
                        </div>
                        <div class="form-group">
                            <label>Current Location</label>
                            <input type="text" name="location" value="${escapeHtml(currentLocation)}" placeholder="San Francisco, CA">
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Education</label>
                        <textarea name="education" rows="3" placeholder="Bachelor's in Computer Science, Stanford University">${escapeHtml(currentEducation)}</textarea>
                    </div>
                    
                    <div class="form-group">
                        <label>About / Bio</label>
                        <textarea name="bio" rows="4" placeholder="Tell us about yourself, your experience, and career goals...">${escapeHtml(currentBio)}</textarea>
                    </div>
                    
                    <div class="form-group">
                        <label>LinkedIn Profile URL</label>
                        <input type="url" name="linkedin" value="${escapeHtml(currentLinkedin)}" placeholder="https://linkedin.com/in/yourprofile">
                    </div>
                    
                    <div class="form-group">
                        <label>Portfolio Website</label>
                        <input type="url" name="portfolio" value="${escapeHtml(currentPortfolio)}" placeholder="https://yourportfolio.com">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                    <button type="submit" class="btn btn-primary">
                        💾 Save Profile
                    </button>
                </div>
            </form>
        </div>
    `;

    document.body.appendChild(modal);
}

// escapeHtml is now provided by shared-utils.js (loaded before this file)
// Duplicate removed — using global escapeHtml() / esc()

async function submitProfileEdit(e) {
    e.preventDefault();
    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner show"></span> Saving...';

    try {
        const formData = new FormData(form);
        const skills = formData.get('skills')
            ? formData.get('skills').split(',').map(s => s.trim()).filter(s => s)
            : [];

        const profileData = {
            first_name: formData.get('firstName'),
            last_name: formData.get('lastName'),
            country_code: formData.get('country_code'),
            phone: formData.get('phone'),
            skills: skills,
            experience: parseFloat(formData.get('experience')) || 0,
            education: formData.get('education'),
            bio: formData.get('bio'),
            location: formData.get('location'),
            linkedin: formData.get('linkedin'),
            portfolio: formData.get('portfolio')
        };

        const response = await fetch(`${API_URL}/candidates/profile`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(profileData)
        });

        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const data = await response.json();

            if (response.ok) {
                showNotification('✓ Profile updated successfully!', 'success');
                form.closest('.modal').remove();
                loadCandidateProfile(); // Reload profile to show updates
            } else {
                throw new Error(data.error || 'Failed to update profile');
            }
        } else {
            throw new Error('Server returned non-JSON response');
        }
    } catch (error) {
        console.error('Profile update error:', error);
        showNotification('Failed to update profile: ' + error.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

function uploadResume() {
    // Create modern upload modal
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Upload resume');
    modal.innerHTML = `
        <div class="modal-content upload-modal">
            <div class="modal-header">
                <h3 class="modal-title">📤 Upload Resume</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <div class="modal-body">
                <div class="upload-zone" id="uploadZone" ondrop="handleDrop(event)" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)">
                    <div class="upload-icon">📄</div>
                    <h4>Drag & Drop your resume here</h4>
                    <p>or click to browse</p>
                    <input type="file" id="resumeFile" accept=".pdf,.doc,.docx" style="display: none" onchange="handleFileSelect(event)">
                    <button class="btn btn-primary" onclick="document.getElementById('resumeFile').click()">
                        Choose File
                    </button>
                    <p class="file-info">Supported formats: PDF, DOC, DOCX (Max 5MB)</p>
                </div>
                <div class="file-preview" id="filePreview" style="display: none;">
                    <div class="preview-header">
                        <div class="file-icon">📄</div>
                        <div class="file-details">
                            <div class="file-name" id="fileName"></div>
                            <div class="file-size" id="fileSize"></div>
                        </div>
                        <button class="btn-remove" onclick="clearFile()">🗑️</button>
                    </div>
                    <div class="upload-progress" id="uploadProgress" style="display: none;">
                        <div class="progress-bar">
                            <div class="progress-fill" id="progressFill"></div>
                        </div>
                        <div class="progress-text" id="progressText">0%</div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                <button class="btn btn-success" id="uploadBtn" onclick="submitResume()" disabled>
                    <span>Upload Resume</span>
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    // Make upload zone clickable
    document.getElementById('uploadZone').onclick = (e) => {
        if (e.target.id === 'uploadZone' || e.target.closest('.upload-icon') || e.target.tagName === 'H4' || e.target.tagName === 'P') {
            document.getElementById('resumeFile').click();
        }
    };
}

let selectedFile = null;

function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        validateAndPreviewFile(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        validateAndPreviewFile(files[0]);
    }
}

function validateAndPreviewFile(file) {
    // Validate file type
    const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    if (!allowedTypes.includes(file.type)) {
        showNotification('Please upload a PDF, DOC, or DOCX file', 'error');
        return;
    }

    // Validate file size (5MB max)
    const maxSize = 5 * 1024 * 1024; // 5MB in bytes
    if (file.size > maxSize) {
        showNotification('File size must be less than 5MB', 'error');
        return;
    }

    // Store file and show preview
    selectedFile = file;
    document.getElementById('uploadZone').style.display = 'none';
    document.getElementById('filePreview').style.display = 'block';
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    document.getElementById('uploadBtn').disabled = false;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function clearFile() {
    selectedFile = null;
    document.getElementById('uploadZone').style.display = 'block';
    document.getElementById('filePreview').style.display = 'none';
    document.getElementById('resumeFile').value = '';
    document.getElementById('uploadBtn').disabled = true;
}

async function submitResume() {
    if (!selectedFile) {
        showNotification('Please select a file first', 'error');
        return;
    }

    const uploadBtn = document.getElementById('uploadBtn');
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<span class="spinner show"></span> Uploading...';

    // Show progress bar
    document.getElementById('uploadProgress').style.display = 'block';

    try {
        const formData = new FormData();
        formData.append('resume', selectedFile);

        // Simulate upload progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 10;
            if (progress <= 90) {
                document.getElementById('progressFill').style.width = progress + '%';
                document.getElementById('progressText').textContent = progress + '%';
            }
        }, 100);

        const response = await fetch(`${API_URL}/candidates/upload-resume`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });

        clearInterval(progressInterval);
        document.getElementById('progressFill').style.width = '100%';
        document.getElementById('progressText').textContent = '100%';

        if (response.ok) {
            const data = await response.json();

            if (data.skills_count > 0) {
                showNotification(`✓ Resume uploaded successfully! Found ${data.skills_count} skills: ${data.skills_found.slice(0, 5).join(', ')}${data.skills_count > 5 ? '...' : ''}`, 'success');
            } else {
                showNotification('✓ Resume uploaded successfully! No technical skills detected. Please add skills manually in your profile.', 'warning');
            }

            // Close modal after short delay
            setTimeout(() => {
                const modal = document.querySelector('.modal');
                if (modal) modal.remove();
                // Refresh profile to show updated resume and skills
                loadCandidateProfile();
            }, 2000);
        } else {
            const error = await response.json();
            throw new Error(error.error || 'Failed to upload resume');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showNotification('Failed to upload resume: ' + error.message, 'error');
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<span>Upload Resume</span>';
        document.getElementById('uploadProgress').style.display = 'none';
    }
}

function candidateLogout() {
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
// CANDIDATE ANALYTICS DASHBOARD
// ============================================
async function loadCandidateAnalytics() {
    const container = document.getElementById('candidateAnalytics');
    container.innerHTML = '<div class="loading">Loading your analytics...</div>';

    try {
        // Fetch candidate data, available jobs, AND assessment sessions in parallel
        const [appsRes, profileRes, jobsRes, assessRes] = await Promise.all([
            fetch(`${API_URL}/candidates/applications`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            }),
            fetch(`${API_URL}/candidates/profile`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            }),
            fetch(`${API_URL}/jobs/list?status=open`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            }),
            // Bug #5 fix: fetch assessment sessions to make recommendations dynamic
            fetch(`${API_URL}/smart-assessments/my-sessions`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            }).catch(() => ({ ok: false }))  // non-blocking if endpoint unavailable
        ]);

        if (!appsRes.ok || !profileRes.ok) {
            throw new Error('Failed to load analytics data');
        }

        const appsData = await appsRes.json();
        const profileData = await profileRes.json();
        const jobsData = jobsRes.ok ? await jobsRes.json() : { jobs: [] };
        // Bug #5 fix: parse assessment sessions for dynamic recommendations
        let assessSessions = [];
        if (assessRes && assessRes.ok) {
            try {
                const assessData = await assessRes.json();
                assessSessions = assessData.sessions || [];
            } catch (_) { /* ignore parse errors */ }
        }

        const applications = appsData.applications || [];
        const profile = profileData.candidate || {};
        const allJobs = jobsData.jobs || [];  // FIX: allJobs is now properly fetched

        // Calculate metrics
        const totalApps = applications.length;
        const shortlisted = applications.filter(a => a.status === 'shortlisted').length;
        const interviewed = applications.filter(a => a.status === 'interviewed' || a.status === 'interview').length;
        const hired = applications.filter(a => a.status === 'hired').length;
        const rejected = applications.filter(a => a.status === 'rejected').length;
        const pending = applications.filter(a => a.status === 'applied' || a.status === 'pending' || a.status === 'submitted').length;

        // Success rates
        const shortlistRate = totalApps > 0 ? ((shortlisted / totalApps) * 100).toFixed(1) : 0;
        const interviewRate = totalApps > 0 ? ((interviewed / totalApps) * 100).toFixed(1) : 0;
        const successRate = totalApps > 0 ? (((shortlisted + interviewed + hired) / totalApps) * 100).toFixed(1) : 0;

        // Average match score - check both possible field names for compatibility
        const avgScore = totalApps > 0 ?
            (applications.reduce((sum, a) => sum + (a.overall_score || a.cci_score || a.match_score || 0), 0) / totalApps).toFixed(1) : 0;

        // Profile completion
        const profileCompletion = calculateProfileCompletion(profile);

        // Matching jobs count
        const candidateSkills = profile.skills || [];
        const matchingJobs = allJobs.filter(job => {
            const jobSkills = job.required_skills || [];
            const matchedSkills = jobSkills.filter(skill =>
                candidateSkills.some(cs => cs.toLowerCase().includes(skill.toLowerCase()) ||
                    skill.toLowerCase().includes(cs.toLowerCase()))
            );
            return matchedSkills.length >= jobSkills.length * 0.5;
        }).length;

        container.innerHTML = `
            <div class="analytics-header">
                <div class="analytics-title">
                    <h2>📊 Your Career Analytics</h2>
                    <p class="subtitle">Track your job search progress and optimize your profile</p>
                </div>
                <div class="analytics-actions">
                    <button class="btn btn-secondary" onclick="exportCandidateReport()">
                        <span>📥</span> Export Report
                    </button>
                </div>
            </div>
            
            <!-- Performance KPIs -->
            <div class="analytics-kpi-grid">
                <div class="kpi-card kpi-primary">
                    <div class="kpi-icon">📋</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${totalApps}</div>
                        <div class="kpi-label">Applications Submitted</div>
                        <div class="kpi-trend ${pending > 0 ? 'positive' : 'neutral'}">
                            <span>${pending > 0 ? '↑' : '→'} ${pending} pending</span>
                        </div>
                    </div>
                </div>
                
                <div class="kpi-card kpi-success">
                    <div class="kpi-icon">✓</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${successRate}%</div>
                        <div class="kpi-label">Success Rate</div>
                        <div class="kpi-trend ${successRate >= 50 ? 'positive' : 'neutral'}">
                            <span>${successRate >= 50 ? '↑' : '→'} ${shortlisted + interviewed + hired} advanced</span>
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
                    <div class="kpi-icon">🎯</div>
                    <div class="kpi-content">
                        <div class="kpi-value">${matchingJobs}</div>
                        <div class="kpi-label">Matching Jobs Available</div>
                        <div class="kpi-trend positive">
                            <span>↑ Based on your skills</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Application Journey -->
            <div class="analytics-section">
                <div class="section-header">
                    <h3>🚀 Your Application Journey</h3>
                    <p>Track your progress through the hiring process</p>
                </div>
                <div class="funnel-container">
                    <div class="funnel-stage" style="width: 100%;">
                        <div class="funnel-bar" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                            <span class="funnel-label">Applied</span>
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
                        <div class="funnel-percent">${totalApps > 0 ? ((hired / totalApps) * 100).toFixed(1) : 0}%</div>
                    </div>
                </div>
            </div>
            
            <!-- Profile & Skills Analysis -->
            <div class="analytics-grid-2">
                <div class="analytics-section">
                    <div class="section-header">
                        <h3>👤 Profile Strength</h3>
                        <p>Complete your profile to increase match rates</p>
                    </div>
                    <div class="profile-strength">
                        <div class="strength-circle">
                            <svg viewBox="0 0 200 200" class="circular-progress">
                                <circle cx="100" cy="100" r="80" fill="none" stroke="#f3f4f6" stroke-width="20"/>
                                <circle cx="100" cy="100" r="80" fill="none" stroke="url(#gradient)" stroke-width="20"
                                    stroke-dasharray="${(profileCompletion / 100) * 502.4} 502.4" 
                                    transform="rotate(-90 100 100)" stroke-linecap="round"/>
                                <defs>
                                    <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" style="stop-color:#667eea"/>
                                        <stop offset="100%" style="stop-color:#764ba2"/>
                                    </linearGradient>
                                </defs>
                            </svg>
                            <div class="strength-value">${profileCompletion}%</div>
                        </div>
                        <div class="strength-tips">
                            <h4>Profile Completion Tips:</h4>
                            <ul>
                                ${!profile.resume_path ? '<li>✕ Upload your resume</li>' : '<li>✓ Resume uploaded</li>'}
                                ${!profile.skills || profile.skills.length === 0 ? '<li>✕ Add your skills</li>' : '<li>✓ Skills added (' + profile.skills.length + ')</li>'}
                                ${!profile.experience ? '<li>✕ Add work experience</li>' : '<li>✓ Experience added</li>'}
                                ${!profile.education ? '<li>✕ Add education details</li>' : '<li>✓ Education added</li>'}
                                ${!profile.phone ? '<li>✕ Add phone number</li>' : '<li>✓ Phone number added</li>'}
                            </ul>
                            <button class="btn btn-primary" onclick="switchCandidateTab('profile', event)">
                                Complete Profile
                            </button>
                        </div>
                    </div>
                </div>
                
                <div class="analytics-section">
                    <div class="section-header">
                        <h3>💼 Application Status</h3>
                        <p>Current state of your applications</p>
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
                                Pending Review
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (pending / totalApps * 100) : 0}%; background: #6b7280;"></div>
                            </div>
                            <div class="decision-value">${pending}</div>
                        </div>
                        
                        <div class="decision-item">
                            <div class="decision-label">
                                <span class="decision-dot" style="background: #ef4444;"></span>
                                Not Selected
                            </div>
                            <div class="decision-bar">
                                <div class="decision-fill" style="width: ${totalApps > 0 ? (rejected / totalApps * 100) : 0}%; background: #ef4444;"></div>
                            </div>
                            <div class="decision-value">${rejected}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Skills Match Analysis -->
            <div class="analytics-section">
                <div class="section-header">
                    <h3>🎯 Skills Match Insights</h3>
                    <p>How your skills compare to job requirements</p>
                </div>
                <div class="skills-insights">
                    ${generateSkillsInsights(applications, profile)}
                </div>
            </div>
            
            <!-- Recommended Actions -->
            <div class="analytics-section">
                <div class="section-header">
                    <h3>💡 Recommended Actions</h3>
                    <p>Personalized tips to improve your job search success</p>
                </div>
                <div class="recommendations-grid">
                    ${generateRecommendations(applications, profile, profileCompletion, avgScore, matchingJobs, assessSessions)}
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Error loading candidate analytics:', error);
        container.innerHTML = `
            <div class="alert alert-error">
                Failed to load analytics. Please try again.
            </div>
        `;
    }
}

/**
 * Calculate profile completion percentage.
 * Bug #3 fix: uses server-provided completion_score when available,
 * falls back to client-side calc with corrected field names.
 * @param {Object} profile - Candidate profile object
 * @returns {number} Completion percentage (0-100)
 */
function calculateProfileCompletion(profile) {
    // Prefer server-computed score (Bug #3 fix)
    if (typeof profile.completion_score === 'number') {
        return profile.completion_score;
    }
    // Fallback: client-side calculation with corrected field names
    let score = 0;
    const factors = [
        profile.resume_file || profile.resume_uploaded || profile.resume_path,
        profile.skills && profile.skills.length > 0,
        profile.experience_years || profile.experience,
        profile.education,
        profile.phone,
        profile.location,
        profile.linkedin,
        profile.bio && profile.bio.length > 50
    ];

    score = (factors.filter(f => f).length / factors.length) * 100;
    return Math.round(score);
}

function generateSkillsInsights(applications, profile) {
    if (applications.length === 0) {
        return '<div class="empty-state">Apply to jobs to see skills match insights</div>';
    }

    // Analyze most common required skills
    const allRequiredSkills = {};
    const candidateSkills = (profile.skills || []).map(s => s.toLowerCase());

    applications.forEach(app => {
        if (app.job_details && app.job_details.required_skills) {
            app.job_details.required_skills.forEach(skill => {
                const skillLower = skill.toLowerCase();
                if (!allRequiredSkills[skillLower]) {
                    allRequiredSkills[skillLower] = {
                        name: skill,
                        count: 0,
                        hasSkill: candidateSkills.some(cs =>
                            cs.includes(skillLower) || skillLower.includes(cs)
                        )
                    };
                }
                allRequiredSkills[skillLower].count++;
            });
        }
    });

    const sortedSkills = Object.values(allRequiredSkills)
        .sort((a, b) => b.count - a.count)
        .slice(0, 8);

    if (sortedSkills.length === 0) {
        return '<div class="empty-state">No skills data available</div>';
    }

    return `
        <div class="skills-grid">
            ${sortedSkills.map(skill => `
                <div class="skill-insight-card ${skill.hasSkill ? 'has-skill' : 'missing-skill'}">
                    <div class="skill-icon">${skill.hasSkill ? '✓' : '+'}</div>
                    <div class="skill-name">${skill.name}</div>
                    <div class="skill-demand">Required in ${skill.count} ${skill.count === 1 ? 'job' : 'jobs'}</div>
                    <div class="skill-status ${skill.hasSkill ? 'positive' : 'neutral'}">
                        ${skill.hasSkill ? 'You have this' : 'Consider learning'}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

/**
 * Generate dynamic recommendation cards based on candidate data.
 * Bug #5 fix: recommendations are fully conditional. 'Take Assessments' only
 * shows when unstarted sessions exist.
 * @param {Array} applications
 * @param {Object} profile
 * @param {number} profileCompletion
 * @param {number} avgScore
 * @param {number} matchingJobs
 * @param {Array} assessSessions - Smart assessment sessions for the candidate
 * @returns {string} HTML string of recommendation cards
 */
function generateRecommendations(applications, profile, profileCompletion, avgScore, matchingJobs, assessSessions = []) {
    const recommendations = [];

    // Profile completion
    if (profileCompletion < 80) {
        recommendations.push({
            icon: '👤',
            title: 'Complete Your Profile',
            desc: `Your profile is ${profileCompletion}% complete. Complete it to increase visibility by up to 40%.`,
            action: 'Complete Profile',
            color: '#667eea',
            onclick: "switchCandidateTab('profile', event)"
        });
    }

    // Match score improvement
    if (avgScore < 70 && avgScore > 0) {
        recommendations.push({
            icon: '⭐',
            title: 'Improve Match Scores',
            desc: 'Your average match score is ' + avgScore + '. Add more relevant skills to increase your match rate.',
            action: 'Update Skills',
            color: '#f59e0b',
            onclick: "switchCandidateTab('profile', event)"
        });
    }

    // More applications
    if (applications.length < 5) {
        recommendations.push({
            icon: '📋',
            title: 'Apply to More Jobs',
            desc: `You've applied to ${applications.length} jobs. Applying to 10-15 jobs increases your chances of success.`,
            action: 'Browse Jobs',
            color: '#10b981',
            onclick: "switchCandidateTab('browse', event)"
        });
    }

    // Matching jobs available
    if (matchingJobs > 0) {
        recommendations.push({
            icon: '🎯',
            title: 'Matching Jobs Available',
            desc: `There are ${matchingJobs} jobs that match your skills. Apply now to increase your chances!`,
            action: 'View Matches',
            color: '#3b82f6',
            onclick: "switchCandidateTab('browse', event)"
        });
    }

    // Bug #5 fix: Only show assessment recommendation if there are unstarted sessions
    const unstartedSessions = assessSessions.filter(
        s => s.status === 'assigned' || s.status === 'in_progress'
    );
    if (unstartedSessions.length > 0) {
        recommendations.push({
            icon: '📝',
            title: `${unstartedSessions.length} Assessment${unstartedSessions.length > 1 ? 's' : ''} Pending`,
            desc: `You have ${unstartedSessions.length} assessment${unstartedSessions.length > 1 ? 's' : ''} waiting. Complete them to advance your applications.`,
            action: 'View Assessments',
            color: '#f093fb',
            onclick: "switchCandidateTab('assessments', event)"
        });
    }

    if (recommendations.length === 0) {
        recommendations.push({
            icon: '🎉',
            title: 'Great Job!',
            desc: 'Your profile is optimized. Keep applying and stay active!',
            action: 'Browse Jobs',
            color: '#10b981',
            onclick: "switchCandidateTab('browse', event)"
        });
    }

    return recommendations.map(rec => `
        <div class="recommendation-card" style="border-left: 4px solid ${rec.color};">
            <div class="rec-icon" style="background: ${rec.color}20;">${rec.icon}</div>
            <div class="rec-content">
                <h4>${rec.title}</h4>
                <p>${rec.desc}</p>
                <button class="btn btn-secondary btn-sm" onclick="${rec.onclick}">
                    ${rec.action}
                </button>
            </div>
        </div>
    `).join('');
}

function exportCandidateReport() {
    try {
        // Gather all applications data from the DOM or re-fetch
        // We'll build CSV from whatever analytics are currently loaded
        const rows = [];
        // Header row
        rows.push(['Application Report - Smart Hiring System']);
        rows.push(['Generated', new Date().toLocaleString()]);
        rows.push([]);
        rows.push(['Job Title', 'Company', 'Status', 'Match Score', 'Applied Date']);

        // Collect application cards from the DOM
        const appCards = document.querySelectorAll('.application-item, .timeline-item, .app-card');
        if (appCards.length > 0) {
            appCards.forEach(card => {
                const title = card.querySelector('h3, h4, .job-title, .app-title')?.textContent?.trim() || 'N/A';
                const company = card.querySelector('.company-name, .company, .subtitle')?.textContent?.trim() || 'N/A';
                const status = card.querySelector('.status-badge, .badge')?.textContent?.trim() || 'N/A';
                const score = card.querySelector('.score, .match-score')?.textContent?.trim() || 'N/A';
                const date = card.querySelector('.date, .applied-date, time')?.textContent?.trim() || 'N/A';
                rows.push([title, company, status, score, date]);
            });
        }

        // Also export KPI summary from analytics if visible
        const kpiCards = document.querySelectorAll('.kpi-card .kpi-value, .stat-value, .metric-value');
        if (kpiCards.length > 0) {
            rows.push([]);
            rows.push(['--- Summary Metrics ---']);
            const kpiLabels = document.querySelectorAll('.kpi-card .kpi-label, .stat-label, .metric-label');
            kpiCards.forEach((kpi, i) => {
                const label = kpiLabels[i]?.textContent?.trim() || `Metric ${i + 1}`;
                rows.push([label, kpi.textContent.trim()]);
            });
        }

        // If no DOM data found, provide a helpful fallback
        if (appCards.length === 0 && kpiCards.length === 0) {
            rows.push(['No application data loaded. Please visit the Analytics tab first.']);
        }

        // Convert to CSV string
        const csv = rows.map(row =>
            row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')
        ).join('\n');

        // Download
        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `candidate_report_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showNotification('Report exported as CSV successfully!', 'success');
    } catch (error) {
        console.error('Export error:', error);
        showNotification('Failed to export report. Please try again.', 'error');
    }
}
