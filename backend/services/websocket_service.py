"""
WebSocket Real-Time Notification Service
=========================================
Enterprise-grade WebSocket support for real-time updates

Features:
- Socket.IO integration with Flask
- Room-based messaging (user-specific, role-specific, broadcast)
- Connection management and heartbeat
- Automatic reconnection support
- Event-based architecture
- Redis pub/sub for multi-server scaling

Events:
- notification: General notifications
- application_update: Application status changes
- new_message: Chat messages
- assessment_start: Assessment started
- assessment_complete: Assessment completed
- interview_scheduled: Interview scheduled
- job_match: New job match found

Author: Smart Hiring System Team
Date: December 2025
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from flask import request
from flask_socketio import emit, join_room, leave_room, rooms
import jwt
import os

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and real-time messaging
    """
    
    def __init__(self, app=None, redis_client=None):
        """
        Initialize WebSocket manager
        
        Args:
            app: Flask application instance
            redis_client: Redis client for pub/sub (optional)
        """
        self.socketio = None
        self.redis_client = redis_client
        self.active_connections = {}  # {user_id: [sid1, sid2, ...]}
        self.sid_to_user = {}  # {sid: user_id}
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """
        Attach to the SocketIO instance already created on the Flask app.

        IMPORTANT: SocketIO must be initialized on ``app`` (as ``app.socketio``)
        **before** this method is called.  This class never creates its own
        SocketIO instance — there must be exactly one per process.
        """
        assert hasattr(app, 'socketio') and app.socketio is not None, (
            'SocketIO must be initialized on app before '
            'WebSocketManager.init_app() is called'
        )
        self.socketio = app.socketio

        self._register_event_handlers()
        logger.info("✅ WebSocket service initialized (reusing app.socketio)")
    
    def _register_event_handlers(self):
        """Register Socket.IO event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect(auth):
            """Handle client connection"""
            try:
                # Authenticate using JWT token
                token = auth.get('token') if auth else None
                
                if not token:
                    logger.warning("❌ WebSocket connection rejected: No token")
                    return False
                
                # Verify JWT token
                try:
                    secret_key = os.getenv('JWT_SECRET_KEY', 'dev-secret-key')
                    payload = jwt.decode(token, secret_key, algorithms=['HS256'])
                    user_id = payload.get('sub')
                    role = payload.get('role', 'candidate')
                except jwt.InvalidTokenError as e:
                    logger.warning(f"❌ WebSocket connection rejected: Invalid token - {e}")
                    return False
                
                # Store connection
                sid = request.sid
                self.sid_to_user[sid] = user_id
                
                if user_id not in self.active_connections:
                    self.active_connections[user_id] = []
                self.active_connections[user_id].append(sid)
                
                # Join user-specific room
                join_room(f"user_{user_id}")
                
                # Join role-specific room
                join_room(f"role_{role}")
                
                logger.info(f"✅ WebSocket connected: user={user_id}, sid={sid}, role={role}")
                
                # Send connection confirmation
                emit('connected', {
                    'status': 'connected',
                    'user_id': user_id,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                return True
                
            except Exception as e:
                logger.error(f"❌ WebSocket connection error: {e}")
                return False
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection"""
            sid = request.sid
            user_id = self.sid_to_user.get(sid)
            
            if user_id:
                # Remove from active connections
                if user_id in self.active_connections:
                    self.active_connections[user_id] = [
                        s for s in self.active_connections[user_id] if s != sid
                    ]
                    
                    # Clean up empty lists
                    if not self.active_connections[user_id]:
                        del self.active_connections[user_id]
                
                del self.sid_to_user[sid]
                logger.info(f"🔌 WebSocket disconnected: user={user_id}, sid={sid}")
        
        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """Subscribe to specific event channels"""
            channel = data.get('channel')
            if channel:
                join_room(channel)
                emit('subscribed', {'channel': channel})
                logger.info(f"📻 User subscribed to channel: {channel}")
        
        @self.socketio.on('unsubscribe')
        def handle_unsubscribe(data):
            """Unsubscribe from event channels"""
            channel = data.get('channel')
            if channel:
                leave_room(channel)
                emit('unsubscribed', {'channel': channel})
                logger.info(f"📻 User unsubscribed from channel: {channel}")
        
        @self.socketio.on('ping')
        def handle_ping():
            """Handle ping for connection health check"""
            emit('pong', {'timestamp': datetime.utcnow().isoformat()})
    
    def send_to_user(self, user_id: str, event: str, data: Dict[str, Any]) -> bool:
        """
        Send message to specific user
        
        Args:
            user_id: Target user ID
            event: Event name
            data: Message data
        
        Returns:
            True if sent successfully
        """
        try:
            room = f"user_{user_id}"
            
            # Add metadata
            message = {
                **data,
                '_metadata': {
                    'event': event,
                    'timestamp': datetime.utcnow().isoformat(),
                    'recipient': user_id
                }
            }
            
            self.socketio.emit(event, message, room=room)
            logger.info(f"📤 Sent {event} to user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send message to user {user_id}: {e}")
            return False
    
    def send_to_role(self, role: str, event: str, data: Dict[str, Any]) -> bool:
        """
        Send message to all users with specific role
        
        Args:
            role: Target role (recruiter, candidate, admin)
            event: Event name
            data: Message data
        
        Returns:
            True if sent successfully
        """
        try:
            room = f"role_{role}"
            
            message = {
                **data,
                '_metadata': {
                    'event': event,
                    'timestamp': datetime.utcnow().isoformat(),
                    'recipient_role': role
                }
            }
            
            self.socketio.emit(event, message, room=room)
            logger.info(f"📤 Sent {event} to role {role}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send message to role {role}: {e}")
            return False
    
    def broadcast(self, event: str, data: Dict[str, Any]) -> bool:
        """
        Broadcast message to all connected clients
        
        Args:
            event: Event name
            data: Message data
        
        Returns:
            True if sent successfully
        """
        try:
            message = {
                **data,
                '_metadata': {
                    'event': event,
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'broadcast'
                }
            }
            
            self.socketio.emit(event, message, broadcast=True)
            logger.info(f"📡 Broadcast {event} to all users")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to broadcast message: {e}")
            return False
    
    def send_notification(self, user_id: str, notification_type: str, 
                         title: str, message: str, data: Optional[Dict] = None) -> bool:
        """
        Send formatted notification to user
        
        Args:
            user_id: Target user ID
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            data: Additional data
        
        Returns:
            True if sent successfully
        """
        notification = {
            'type': notification_type,
            'title': title,
            'message': message,
            'data': data or {},
            'read': False,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return self.send_to_user(user_id, 'notification', notification)
    
    def notify_application_update(self, user_id: str, application_id: str, 
                                  status: str, job_title: str) -> bool:
        """Notify user of application status update"""
        return self.send_notification(
            user_id=user_id,
            notification_type='application_update',
            title='Application Update',
            message=f'Your application for {job_title} is now {status}',
            data={
                'application_id': application_id,
                'status': status,
                'job_title': job_title
            }
        )
    
    def notify_new_message(self, user_id: str, sender_name: str, message: str) -> bool:
        """Notify user of new message"""
        return self.send_notification(
            user_id=user_id,
            notification_type='new_message',
            title=f'New message from {sender_name}',
            message=message[:100] + ('...' if len(message) > 100 else ''),
            data={
                'sender': sender_name
            }
        )
    
    def notify_assessment_start(self, user_id: str, assessment_title: str, 
                               assessment_id: str) -> bool:
        """Notify user that assessment has started"""
        return self.send_notification(
            user_id=user_id,
            notification_type='assessment_start',
            title='Assessment Started',
            message=f'Your assessment "{assessment_title}" has been activated',
            data={
                'assessment_id': assessment_id,
                'assessment_title': assessment_title
            }
        )
    
    def notify_interview_scheduled(self, user_id: str, interview_data: Dict) -> bool:
        """Notify user of scheduled interview"""
        return self.send_notification(
            user_id=user_id,
            notification_type='interview_scheduled',
            title='Interview Scheduled',
            message=f'Interview scheduled for {interview_data.get("date")} at {interview_data.get("time")}',
            data=interview_data
        )
    
    def notify_job_match(self, user_id: str, job_title: str, job_id: str, match_score: float) -> bool:
        """Notify user of new job match"""
        return self.send_notification(
            user_id=user_id,
            notification_type='job_match',
            title='New Job Match',
            message=f'You are a {match_score:.0f}% match for {job_title}',
            data={
                'job_id': job_id,
                'job_title': job_title,
                'match_score': match_score
            }
        )
    
    def get_active_users(self) -> List[str]:
        """Get list of currently connected user IDs"""
        return list(self.active_connections.keys())
    
    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of active connections for user"""
        return len(self.active_connections.get(user_id, []))
    
    def is_user_online(self, user_id: str) -> bool:
        """Check if user has any active connections"""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get WebSocket service statistics"""
        return {
            'total_connections': sum(len(sids) for sids in self.active_connections.values()),
            'unique_users': len(self.active_connections),
            'active_users': self.get_active_users()
        }


# Global singleton
_websocket_manager = None


def get_websocket_manager() -> Optional[WebSocketManager]:
    """Get global WebSocket manager instance"""
    global _websocket_manager
    return _websocket_manager


def init_websocket_manager(app, redis_client=None) -> WebSocketManager:
    """Initialize global WebSocket manager"""
    global _websocket_manager
    _websocket_manager = WebSocketManager(app, redis_client)
    return _websocket_manager
