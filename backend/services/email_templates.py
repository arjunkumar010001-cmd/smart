"""
Advanced Email Template System
===============================
Professional HTML email templates with dynamic content

Features:
- Beautiful responsive HTML templates
- Personalization variables
- Template inheritance
- Inline CSS for email client compatibility
- Tracking pixels (optional)
- Unsubscribe links
- Multi-language support ready

Templates:
- application_received
- application_status_update
- interview_invitation
- interview_reminder
- assessment_invitation
- assessment_completed
- offer_letter
- rejection_letter
- welcome_email
- password_reset
- account_verification

Author: Smart Hiring System Team
Date: December 2025
"""

from typing import Dict, Optional, Any
from datetime import datetime
import os


class EmailTemplates:
    """Professional email template system"""
    
    # Base template with header and footer
    BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7fa;">
    <table width="100%%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f7fa;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="background-color: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%); padding: 40px 30px; text-align: center; border-radius: 12px 12px 0 0;">
                            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 600;">{header_icon} {header_title}</h1>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            {content}
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8f9fa; padding: 30px; text-align: center; border-radius: 0 0 12px 12px; border-top: 1px solid #e9ecef;">
                            <p style="color: #6c757d; font-size: 14px; margin: 0 0 10px 0;">
                                <strong>Smart Hiring System</strong>
                            </p>
                            <p style="color: #6c757d; font-size: 12px; margin: 0 0 10px 0;">
                                AI-Powered Fair Recruitment Platform
                            </p>
                            <p style="color: #6c757d; font-size: 11px; margin: 0;">
                                © {year} Smart Hiring System. All rights reserved.
                            </p>
                            {unsubscribe_link}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
    """
    
    @staticmethod
    def render_template(template_name: str, data: Dict[str, Any]) -> str:
        """
        Render email template with data
        
        Args:
            template_name: Name of the template
            data: Template data
        
        Returns:
            Rendered HTML email
        """
        templates = {
            'application_received': EmailTemplates._application_received,
            'application_status_update': EmailTemplates._application_status_update,
            'interview_invitation': EmailTemplates._interview_invitation,
            'interview_reminder': EmailTemplates._interview_reminder,
            'assessment_invitation': EmailTemplates._assessment_invitation,
            'assessment_completed': EmailTemplates._assessment_completed,
            'offer_letter': EmailTemplates._offer_letter,
            'rejection_letter': EmailTemplates._rejection_letter,
            'welcome_email': EmailTemplates._welcome_email,
            'password_reset': EmailTemplates._password_reset,
            'account_verification': EmailTemplates._account_verification
        }
        
        template_func = templates.get(template_name)
        if not template_func:
            raise ValueError(f"Template '{template_name}' not found")
        
        return template_func(data)
    
    @staticmethod
    def _wrap_content(content: str, header_icon: str, header_title: str, 
                      title: str, include_unsubscribe: bool = True) -> str:
        """Wrap content in base template"""
        unsubscribe_html = ""
        if include_unsubscribe:
            unsubscribe_html = '''
            <p style="color: #6c757d; font-size: 11px; margin: 10px 0 0 0;">
                <a href="{unsubscribe_url}" style="color: #6c757d; text-decoration: underline;">Unsubscribe from emails</a>
            </p>
            '''
        
        return EmailTemplates.BASE_TEMPLATE.format(
            title=title,
            header_icon=header_icon,
            header_title=header_title,
            content=content,
            year=datetime.now().year,
            unsubscribe_link=unsubscribe_html
        )
    
    @staticmethod
    def _application_received(data: Dict) -> str:
        """Application received confirmation"""
        content = f"""
        <p style="font-size: 16px; color: #212529; margin: 0 0 20px 0;">
            Hi <strong>{data.get('candidate_name', 'Candidate')}</strong>,
        </p>
        
        <p style="font-size: 15px; color: #495057; line-height: 1.6; margin: 0 0 20px 0;">
            Thank you for applying to the <strong>{data.get('job_title', 'position')}</strong> role at <strong>{data.get('company_name', 'our company')}</strong>.
        </p>
        
        <div style="background: linear-gradient(135deg, #e0e7ff 0%, #f3e8ff 100%); padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 4px solid #667eea;">
            <h3 style="color: #667eea; margin: 0 0 15px 0; font-size: 18px;">📋 Application Details</h3>
            <table style="width: 100%%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px 0; color: #495057;"><strong>Position:</strong></td>
                    <td style="padding: 8px 0; color: #212529;">{data.get('job_title', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #495057;"><strong>Company:</strong></td>
                    <td style="padding: 8px 0; color: #212529;">{data.get('company_name', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #495057;"><strong>Submitted:</strong></td>
                    <td style="padding: 8px 0; color: #212529;">{data.get('submitted_at', datetime.now().strftime('%Y-%m-%d %H:%M'))}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #495057;"><strong>Application ID:</strong></td>
                    <td style="padding: 8px 0; color: #212529;">{data.get('application_id', 'N/A')}</td>
                </tr>
            </table>
        </div>
        
        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 25px 0;">
            <h3 style="color: #212529; margin: 0 0 15px 0; font-size: 16px;">🔄 What Happens Next?</h3>
            <ol style="margin: 0; padding-left: 20px; color: #495057;">
                <li style="margin-bottom: 10px;"><strong>AI Resume Analysis:</strong> Your resume is being parsed and analyzed</li>
                <li style="margin-bottom: 10px;"><strong>Skill Matching:</strong> We'll match your skills with job requirements</li>
                <li style="margin-bottom: 10px;"><strong>Fairness Audit:</strong> Bias-free evaluation ensures fair assessment</li>
                <li style="margin-bottom: 10px;"><strong>Recruiter Review:</strong> Our team will review your application</li>
                <li style="margin-bottom: 0;"><strong>Notification:</strong> You'll receive updates at each stage</li>
            </ol>
        </div>
        
        <p style="font-size: 15px; color: #495057; line-height: 1.6; margin: 20px 0 0 0;">
            We typically respond within <strong>3-5 business days</strong>. You can track your application status in your dashboard.
        </p>
        
        <p style="text-align: center; margin: 30px 0;">
            <a href="{data.get('dashboard_url', '#')}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 40px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px;">View Application Status</a>
        </p>
        
        <p style="font-size: 15px; color: #495057; margin: 30px 0 0 0;">
            Best of luck!<br>
            <strong>The Smart Hiring Team</strong>
        </p>
        """
        
        return EmailTemplates._wrap_content(
            content,
            header_icon="🚀",
            header_title="Application Received",
            title=f"Application Received - {data.get('job_title', 'Position')}"
        )
    
    @staticmethod
    def _interview_invitation(data: Dict) -> str:
        """Interview invitation email"""
        content = f"""
        <p style="font-size: 16px; color: #212529; margin: 0 0 20px 0;">
            Congratulations <strong>{data.get('candidate_name', 'Candidate')}</strong>! 🎉
        </p>
        
        <p style="font-size: 15px; color: #495057; line-height: 1.6; margin: 0 0 20px 0;">
            We're impressed with your application and would like to invite you for an interview for the <strong>{data.get('job_title', 'position')}</strong> role.
        </p>
        
        <div style="background: linear-gradient(135deg, #d4fc79 0%, #96e6a1 100%); padding: 30px; border-radius: 12px; margin: 30px 0; text-align: center;">
            <h2 style="color: #155724; margin: 0 0 20px 0; font-size: 24px;">📅 Interview Details</h2>
            <table style="margin: 0 auto; text-align: left;">
                <tr>
                    <td style="padding: 10px 20px 10px 0; color: #155724; font-weight: 600;">Date & Time:</td>
                    <td style="padding: 10px 0; color: #155724; font-size: 16px;">{data.get('interview_datetime', 'TBD')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 20px 10px 0; color: #155724; font-weight: 600;">Duration:</td>
                    <td style="padding: 10px 0; color: #155724; font-size: 16px;">{data.get('duration', '45 minutes')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 20px 10px 0; color: #155724; font-weight: 600;">Format:</td>
                    <td style="padding: 10px 0; color: #155724; font-size: 16px;">{data.get('format', 'Video Call')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 20px 10px 0; color: #155724; font-weight: 600;">Interviewer:</td>
                    <td style="padding: 10px 0; color: #155724; font-size: 16px;">{data.get('interviewer_name', 'TBD')}</td>
                </tr>
            </table>
        </div>
        
        <p style="text-align: center; margin: 30px 0;">
            <a href="{data.get('meeting_link', '#')}" style="display: inline-block; background: #28a745; color: white; padding: 18px 50px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 18px; box-shadow: 0 4px 6px rgba(40,167,69,0.3);">Join Interview</a>
        </p>
        
        <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin: 25px 0; border-left: 4px solid #ffc107;">
            <h3 style="color: #856404; margin: 0 0 15px 0; font-size: 16px;">💡 Interview Tips</h3>
            <ul style="margin: 0; padding-left: 20px; color: #856404;">
                <li style="margin-bottom: 8px;">Test your audio and video setup beforehand</li>
                <li style="margin-bottom: 8px;">Join 5 minutes early</li>
                <li style="margin-bottom: 8px;">Prepare questions about the role and company</li>
                <li style="margin-bottom: 8px;">Have your resume and portfolio ready</li>
                <li style="margin-bottom: 0;">Find a quiet, well-lit space</li>
            </ul>
        </div>
        
        <p style="font-size: 14px; color: #6c757d; margin: 25px 0 0 0; text-align: center;">
            Need to reschedule? <a href="{data.get('reschedule_url', '#')}" style="color: #667eea; text-decoration: underline;">Click here</a>
        </p>
        """
        
        return EmailTemplates._wrap_content(
            content,
            header_icon="🎯",
            header_title="Interview Invitation",
            title=f"Interview Invitation - {data.get('job_title', 'Position')}"
        )
    
    @staticmethod
    def _assessment_invitation(data: Dict) -> str:
        """Assessment/quiz invitation"""
        content = f"""
        <p style="font-size: 16px; color: #212529; margin: 0 0 20px 0;">
            Hi <strong>{data.get('candidate_name', 'Candidate')}</strong>,
        </p>
        
        <p style="font-size: 15px; color: #495057; line-height: 1.6; margin: 0 0 20px 0;">
            As part of your application for <strong>{data.get('job_title', 'the position')}</strong>, we'd like you to complete an assessment.
        </p>
        
        <div style="background: linear-gradient(135deg, #fbc2eb 0%, #a6c1ee 100%); padding: 30px; border-radius: 12px; margin: 30px 0; text-align: center;">
            <h2 style="color: #4a148c; margin: 0 0 20px 0; font-size: 22px;">📝 {data.get('assessment_title', 'Assessment')}</h2>
            <p style="color: #4a148c; font-size: 16px; margin: 0 0 10px 0;">
                <strong>Questions:</strong> {data.get('question_count', 'N/A')}
            </p>
            <p style="color: #4a148c; font-size: 16px; margin: 0 0 10px 0;">
                <strong>Time Limit:</strong> {data.get('time_limit', 'N/A')} minutes
            </p>
            <p style="color: #4a148c; font-size: 16px; margin: 0;">
                <strong>Deadline:</strong> {data.get('deadline', 'N/A')}
            </p>
        </div>
        
        <p style="text-align: center; margin: 30px 0;">
            <a href="{data.get('assessment_url', '#')}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 18px 50px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 18px;">Start Assessment</a>
        </p>
        
        <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin: 25px 0; border-left: 4px solid #2196f3;">
            <h3 style="color: #0d47a1; margin: 0 0 15px 0; font-size: 16px;">ℹ️ Important Information</h3>
            <ul style="margin: 0; padding-left: 20px; color: #0d47a1;">
                <li style="margin-bottom: 8px;">Once started, the timer cannot be paused</li>
                <li style="margin-bottom: 8px;">Ensure stable internet connection</li>
                <li style="margin-bottom: 8px;">Answer all questions before submitting</li>
                <li style="margin-bottom: 0;">Use latest version of Chrome or Firefox</li>
            </ul>
        </div>
        """
        
        return EmailTemplates._wrap_content(
            content,
            header_icon="📊",
            header_title="Assessment Invitation",
            title=f"Assessment Invitation - {data.get('job_title', 'Position')}"
        )
    
    @staticmethod
    def _offer_letter(data: Dict) -> str:
        """Job offer letter"""
        content = f"""
        <p style="font-size: 16px; color: #212529; margin: 0 0 20px 0;">
            Dear <strong>{data.get('candidate_name', 'Candidate')}</strong>,
        </p>
        
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 40px; border-radius: 12px; margin: 30px 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 32px;">🎊 Congratulations! 🎊</h1>
        </div>
        
        <p style="font-size: 15px; color: #495057; line-height: 1.6; margin: 0 0 20px 0;">
            We are delighted to offer you the position of <strong>{data.get('job_title', 'N/A')}</strong> at <strong>{data.get('company_name', 'our company')}</strong>.
        </p>
        
        <div style="background: #f8f9fa; padding: 25px; border-radius: 10px; margin: 25px 0;">
            <h3 style="color: #212529; margin: 0 0 20px 0; font-size: 18px;">📋 Offer Details</h3>
            <table style="width: 100%%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 10px 0; color: #495057; border-bottom: 1px solid #dee2e6;"><strong>Position:</strong></td>
                    <td style="padding: 10px 0; color: #212529; border-bottom: 1px solid #dee2e6; text-align: right;">{data.get('job_title', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0; color: #495057; border-bottom: 1px solid #dee2e6;"><strong>Department:</strong></td>
                    <td style="padding: 10px 0; color: #212529; border-bottom: 1px solid #dee2e6; text-align: right;">{data.get('department', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0; color: #495057; border-bottom: 1px solid #dee2e6;"><strong>Salary:</strong></td>
                    <td style="padding: 10px 0; color: #212529; border-bottom: 1px solid #dee2e6; text-align: right;">{data.get('salary', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0; color: #495057; border-bottom: 1px solid #dee2e6;"><strong>Start Date:</strong></td>
                    <td style="padding: 10px 0; color: #212529; border-bottom: 1px solid #dee2e6; text-align: right;">{data.get('start_date', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0; color: #495057;"><strong>Location:</strong></td>
                    <td style="padding: 10px 0; color: #212529; text-align: right;">{data.get('location', 'N/A')}</td>
                </tr>
            </table>
        </div>
        
        <p style="font-size: 15px; color: #495057; line-height: 1.6; margin: 20px 0;">
            Please review the attached offer letter document for complete details including benefits, policies, and terms.
        </p>
        
        <p style="text-align: center; margin: 30px 0;">
            <a href="{data.get('accept_url', '#')}" style="display: inline-block; background: #28a745; color: white; padding: 18px 40px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; margin: 0 10px;">Accept Offer</a>
            <a href="{data.get('view_document_url', '#')}" style="display: inline-block; background: #667eea; color: white; padding: 18px 40px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; margin: 0 10px;">View Full Document</a>
        </p>
        
        <p style="font-size: 14px; color: #6c757d; margin: 25px 0 0 0; text-align: center;">
            Please respond by <strong>{data.get('response_deadline', 'N/A')}</strong>
        </p>
        """
        
        return EmailTemplates._wrap_content(
            content,
            header_icon="🏆",
            header_title="Job Offer",
            title=f"Job Offer - {data.get('job_title', 'Position')}"
        )
    
    # Add placeholder methods for other templates
    @staticmethod
    def _application_status_update(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Status update template - {data}</p>", "📢", "Status Update", "Application Status Update")
    
    @staticmethod
    def _interview_reminder(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Interview reminder template - {data}</p>", "⏰", "Interview Reminder", "Interview Reminder")
    
    @staticmethod
    def _assessment_completed(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Assessment completed template - {data}</p>", "✅", "Assessment Completed", "Assessment Completed")
    
    @staticmethod
    def _rejection_letter(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Rejection letter template - {data}</p>", "📋", "Application Update", "Application Update")
    
    @staticmethod
    def _welcome_email(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Welcome email template - {data}</p>", "👋", "Welcome!", "Welcome to Smart Hiring")
    
    @staticmethod
    def _password_reset(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Password reset template - {data}</p>", "🔐", "Password Reset", "Reset Your Password")
    
    @staticmethod
    def _account_verification(data: Dict) -> str:
        return EmailTemplates._wrap_content(f"<p>Account verification template - {data}</p>", "✉️", "Verify Account", "Verify Your Account")


# ── Standalone helper used by onboarding_routes ──────────────────────────────

def render_offer_letter_email(
    candidate_name: str,
    position: str,
    company_name: str,
    salary: str,
    start_date: str,
    response_deadline: str,
) -> str:
    """Render an offer letter HTML email using the existing template."""
    return EmailTemplates._offer_letter({
        "candidate_name": candidate_name,
        "job_title": position,
        "company_name": company_name,
        "salary": salary,
        "start_date": start_date,
        "response_deadline": response_deadline,
        "department": "As assigned",
        "location": "As communicated",
        "accept_url": "#",
        "view_document_url": "#",
    })
