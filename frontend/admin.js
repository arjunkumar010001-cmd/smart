/**
 * Admin Dashboard JavaScript
 * Handles all admin-specific functionality
 */

// Track loaded stats
let adminStats = { totalUsers: 0, activeJobs: 0, applications: 0 };

async function loadAdminDashboard() {
    console.log('Loading Admin Dashboard...');
    const app = document.getElementById('app');

    // First render the dashboard with loading state
    app.innerHTML = `
        <div style="padding: 40px; max-width: 1200px; margin: 0 auto; font-family: system-ui, -apple-system, sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
                <h1 style="color: #4F46E5; margin: 0;">Admin Dashboard</h1>
                <button onclick="adminLogout()" style="padding: 10px 20px; background: #ef4444; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500;">Logout</button>
            </div>
            
            <div style="background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px;">
                <h2 style="margin: 0 0 15px 0; color: #1f2937;">Welcome, ${currentUser?.full_name || 'Administrator'}!</h2>
                <p style="color: #6b7280; margin: 5px 0;">📧 Email: ${currentUser?.email || ''}</p>
                <p style="color: #6b7280; margin: 5px 0;">👤 Role: Administrator</p>
            </div>
            
            <div id="deploymentStatus" style="background: #f0fdf4; padding: 30px; border-radius: 12px; border: 2px solid #86efac; margin-bottom: 20px;">
                <h3 style="margin: 0 0 15px 0; color: #15803d;">🎉 System Active</h3>
                <p style="margin: 10px 0; color: #166534;">Your Smart Hiring System is running successfully!</p>
            </div>
            
            <div style="background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px;">
                <h3 style="margin: 0 0 20px 0; color: #1f2937;">📊 Quick Stats</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                    <div style="background: #f3f4f6; padding: 20px; border-radius: 8px;">
                        <div style="color: #6b7280; font-size: 14px; margin-bottom: 5px;">Total Users</div>
                        <div id="statTotalUsers" style="font-size: 28px; font-weight: bold; color: #4F46E5;">
                            <span class="loading-spinner">⏳</span>
                        </div>
                    </div>
                    <div style="background: #f3f4f6; padding: 20px; border-radius: 8px;">
                        <div style="color: #6b7280; font-size: 14px; margin-bottom: 5px;">Active Jobs</div>
                        <div id="statActiveJobs" style="font-size: 28px; font-weight: bold; color: #10b981;">
                            <span class="loading-spinner">⏳</span>
                        </div>
                    </div>
                    <div style="background: #f3f4f6; padding: 20px; border-radius: 8px;">
                        <div style="color: #6b7280; font-size: 14px; margin-bottom: 5px;">Applications</div>
                        <div id="statApplications" style="font-size: 28px; font-weight: bold; color: #f59e0b;">
                            <span class="loading-spinner">⏳</span>
                        </div>
                    </div>
                </div>
                <p id="statsStatus" style="margin-top: 20px; color: #9ca3af; font-size: 13px; text-align: center;">
                    Loading statistics...
                </p>
                
                <!-- Analytics Chart -->
                <div style="margin-top: 30px; height: 300px; position: relative;">
                    <canvas id="adminStatsChart"></canvas>
                </div>
            </div>
            
            <div style="background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h3 style="margin: 0 0 20px 0; color: #1f2937;">🔧 Admin Actions</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <button onclick="loadAdminUsers()" style="padding: 15px; background: #4F46E5; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        👥 Manage Users
                    </button>
                    <button onclick="loadAdminJobs()" style="padding: 15px; background: #10b981; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        💼 View All Jobs
                    </button>
                    <button onclick="refreshAdminStats()" style="padding: 15px; background: #6366f1; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 500;">
                        🔄 Refresh Stats
                    </button>
                </div>
            </div>
        </div>
    `;

    // Now fetch actual stats
    await loadAdminStats();
}

async function loadAdminStats() {
    try {
        const response = await fetch(`${API_URL}/admin/stats`, {
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();
            updateStatsDisplay(data);
        } else {
            // Fallback - try to get data from other endpoints
            await loadStatsFallback();
        }
    } catch (error) {
        console.error('Error loading admin stats:', error);
        await loadStatsFallback();
    }
}

async function loadStatsFallback() {
    // Try to get stats from individual endpoints
    let totalUsers = 0, activeJobs = 0, applications = 0;

    try {
        // Get analytics which might include stats
        const analyticsResponse = await fetch(`${API_URL}/dashboard/analytics`, {
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (analyticsResponse.ok) {
            const analytics = await analyticsResponse.json();
            activeJobs = analytics.summary?.total_jobs || 0;
            applications = analytics.summary?.total_applications || 0;
        }
    } catch (e) {
        console.log('Analytics endpoint not available');
    }

    updateStatsDisplay({
        total_users: totalUsers,
        active_jobs: activeJobs,
        total_applications: applications
    });
}

function updateStatsDisplay(data) {
    const totalUsersEl = document.getElementById('statTotalUsers');
    const activeJobsEl = document.getElementById('statActiveJobs');
    const applicationsEl = document.getElementById('statApplications');
    const statusEl = document.getElementById('statsStatus');

    if (totalUsersEl) totalUsersEl.textContent = data.total_users || data.totalUsers || '0';
    if (activeJobsEl) activeJobsEl.textContent = data.active_jobs || data.activeJobs || '0';
    if (applicationsEl) applicationsEl.textContent = data.total_applications || data.applications || '0';
    if (statusEl) statusEl.textContent = 'Last updated: ' + new Date().toLocaleTimeString();

    adminStats = {
        totalUsers: data.total_users || 0,
        activeJobs: data.active_jobs || 0,
        applications: data.total_applications || 0
    };

    // Render Chart
    renderAdminChart(adminStats);
}

function renderAdminChart(stats) {
    const ctx = document.getElementById('adminStatsChart');
    if (!ctx) return;

    // Destroy existing chart if any
    if (window.adminChartInstance) {
        window.adminChartInstance.destroy();
    }

    // Check if dark mode is active to style chart
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#e5e7eb' : '#374151';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';

    window.adminChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Total Users', 'Active Jobs', 'Applications'],
            datasets: [{
                label: 'System Metrics',
                data: [stats.totalUsers, stats.activeJobs, stats.applications],
                backgroundColor: [
                    'rgba(79, 70, 229, 0.8)', // Primary
                    'rgba(16, 185, 129, 0.8)', // Success
                    'rgba(245, 158, 11, 0.8)'  // Warning
                ],
                borderColor: [
                    'rgba(79, 70, 229, 1)',
                    'rgba(16, 185, 129, 1)',
                    'rgba(245, 158, 11, 1)'
                ],
                borderWidth: 1,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: 'Platform Overview',
                    color: textColor,
                    font: {
                        family: "'Plus Jakarta Sans', sans-serif",
                        size: 16,
                        weight: '600'
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: gridColor
                    },
                    ticks: {
                        color: textColor,
                        precision: 0
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: textColor
                    }
                }
            },
            animation: {
                duration: 2000,
                easing: 'easeOutQuart'
            }
        }
    });
}

async function refreshAdminStats() {
    const statusEl = document.getElementById('statsStatus');
    if (statusEl) statusEl.textContent = 'Refreshing...';
    await loadAdminStats();
}

async function loadAdminUsers() {
    showNotification('Loading user management...', 'info');
    // This can be expanded to show a full user management interface
}

async function loadAdminJobs() {
    showNotification('Loading job listings...', 'info');
    // This can be expanded to show all jobs across the platform
}

function adminLogout() {
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
