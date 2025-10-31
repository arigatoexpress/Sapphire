import React, { useState, useEffect } from 'react';

interface Notification {
  id: string;
  type: 'success' | 'warning' | 'error' | 'info';
  title: string;
  message: string;
  timestamp: Date;
  read: boolean;
}

interface NotificationCenterProps {
  alerts?: string[];
}

const NotificationCenter: React.FC<NotificationCenterProps> = ({ alerts = [] }) => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  // Convert alerts to notifications
  useEffect(() => {
    const newNotifications: Notification[] = alerts.map((alert, index) => ({
      id: `alert-${Date.now()}-${index}`,
      type: alert.includes('⚠️') ? 'warning' :
            alert.includes('🎯') ? 'success' :
            alert.includes('❌') ? 'error' : 'info',
      title: alert.includes('⚠️') ? 'Risk Alert' :
             alert.includes('🎯') ? 'Target Achieved' :
             alert.includes('❌') ? 'Error' : 'System Info',
      message: alert.replace(/^[⚠️🎯ℹ️❌]\s*/, ''),
      timestamp: new Date(),
      read: false
    }));

    if (newNotifications.length > 0) {
      setNotifications(prev => [...newNotifications, ...prev].slice(0, 50)); // Keep last 50
    }
  }, [alerts]);

  // Add some sample notifications for demo
  useEffect(() => {
    const sampleNotifications: Notification[] = [
      {
        id: 'sample-1',
        type: 'success',
        title: 'Trade Executed',
        message: 'DeepSeek model successfully executed BTC/USDT long position',
        timestamp: new Date(Date.now() - 5 * 60 * 1000), // 5 minutes ago
        read: false
      },
      {
        id: 'sample-2',
        type: 'warning',
        title: 'High Volatility Detected',
        message: 'BTC/USDT volatility exceeded 2x normal range',
        timestamp: new Date(Date.now() - 15 * 60 * 1000), // 15 minutes ago
        read: true
      },
      {
        id: 'sample-3',
        type: 'info',
        title: 'Model Performance Update',
        message: 'Qwen2.5-Coder achieved 68% win rate this hour',
        timestamp: new Date(Date.now() - 30 * 60 * 1000), // 30 minutes ago
        read: true
      }
    ];

    setNotifications(prev => [...sampleNotifications, ...prev].slice(0, 50));
  }, []);

  const unreadCount = notifications.filter(n => !n.read).length;

  const filteredNotifications = notifications.filter(n =>
    filter === 'all' || (filter === 'unread' && !n.read)
  );

  const markAsRead = (id: string) => {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    );
  };

  const markAllAsRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const getTypeColor = (type: Notification['type']) => {
    switch (type) {
      case 'success': return 'text-green-600 bg-green-50 border-green-200';
      case 'warning': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case 'error': return 'text-red-600 bg-red-50 border-red-200';
      case 'info': return 'text-blue-600 bg-blue-50 border-blue-200';
    }
  };

  const getTypeIcon = (type: Notification['type']) => {
    switch (type) {
      case 'success': return '✅';
      case 'warning': return '⚠️';
      case 'error': return '❌';
      case 'info': return 'ℹ️';
    }
  };

  return (
    <div className="relative">
      {/* Notification Button */}
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="relative p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
        title="Notifications"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-5-5V12a7 7 0 00-14 0v5l-5 5h5m0 0v1a3 3 0 006 0v-1m-6-4h6" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Notification Dropdown */}
      {showDropdown && (
        <div className="absolute right-0 mt-2 w-96 bg-white rounded-lg shadow-lg border border-slate-200 z-50">
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900">Notifications</h3>
              <div className="flex items-center space-x-2">
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as 'all' | 'unread')}
                  className="px-2 py-1 text-sm border border-slate-300 rounded"
                >
                  <option value="all">All</option>
                  <option value="unread">Unread</option>
                </select>
                {unreadCount > 0 && (
                  <button
                    onClick={markAllAsRead}
                    className="text-sm text-blue-600 hover:text-blue-800"
                  >
                    Mark all read
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {filteredNotifications.length === 0 ? (
              <div className="p-4 text-center text-slate-500">
                <span className="text-2xl mb-2 block">📭</span>
                <p>No notifications</p>
              </div>
            ) : (
              filteredNotifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`p-4 border-b border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors ${
                    !notification.read ? 'bg-blue-50' : ''
                  }`}
                  onClick={() => markAsRead(notification.id)}
                >
                  <div className="flex items-start space-x-3">
                    <span className="text-lg flex-shrink-0">{getTypeIcon(notification.type)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-medium text-slate-900 truncate">
                          {notification.title}
                        </h4>
                        {!notification.read && (
                          <div className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0"></div>
                        )}
                      </div>
                      <p className="text-sm text-slate-600 mt-1">{notification.message}</p>
                      <p className="text-xs text-slate-500 mt-2">
                        {notification.timestamp.toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {filteredNotifications.length > 0 && (
            <div className="p-3 border-t border-slate-200 text-center">
              <button
                onClick={() => setShowDropdown(false)}
                className="text-sm text-slate-600 hover:text-slate-900"
              >
                Close
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
