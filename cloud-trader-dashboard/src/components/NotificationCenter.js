import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
const NotificationCenter = ({ alerts = [] }) => {
    const [notifications, setNotifications] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [filter, setFilter] = useState('all');
    // Convert alerts to notifications
    useEffect(() => {
        const newNotifications = alerts.map((alert, index) => ({
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
        const sampleNotifications = [
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
    const filteredNotifications = notifications.filter(n => filter === 'all' || (filter === 'unread' && !n.read));
    const markAsRead = (id) => {
        setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    };
    const markAllAsRead = () => {
        setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    };
    const getTypeColor = (type) => {
        switch (type) {
            case 'success': return 'text-green-600 bg-green-50 border-green-200';
            case 'warning': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
            case 'error': return 'text-red-600 bg-red-50 border-red-200';
            case 'info': return 'text-blue-600 bg-blue-50 border-blue-200';
        }
    };
    const getTypeIcon = (type) => {
        switch (type) {
            case 'success': return '✅';
            case 'warning': return '⚠️';
            case 'error': return '❌';
            case 'info': return 'ℹ️';
        }
    };
    return (_jsxs("div", { className: "relative", children: [_jsxs("button", { onClick: () => setShowDropdown(!showDropdown), className: "relative p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors", title: "Notifications", children: [_jsx("svg", { className: "w-6 h-6", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M15 17h5l-5-5V12a7 7 0 00-14 0v5l-5 5h5m0 0v1a3 3 0 006 0v-1m-6-4h6" }) }), unreadCount > 0 && (_jsx("span", { className: "absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center", children: unreadCount > 9 ? '9+' : unreadCount }))] }), showDropdown && (_jsxs("div", { className: "absolute right-0 mt-2 w-96 bg-white rounded-lg shadow-lg border border-slate-200 z-50", children: [_jsx("div", { className: "p-4 border-b border-slate-200", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900", children: "Notifications" }), _jsxs("div", { className: "flex items-center space-x-2", children: [_jsxs("select", { value: filter, onChange: (e) => setFilter(e.target.value), className: "px-2 py-1 text-sm border border-slate-300 rounded", children: [_jsx("option", { value: "all", children: "All" }), _jsx("option", { value: "unread", children: "Unread" })] }), unreadCount > 0 && (_jsx("button", { onClick: markAllAsRead, className: "text-sm text-blue-600 hover:text-blue-800", children: "Mark all read" }))] })] }) }), _jsx("div", { className: "max-h-96 overflow-y-auto", children: filteredNotifications.length === 0 ? (_jsxs("div", { className: "p-4 text-center text-slate-500", children: [_jsx("span", { className: "text-2xl mb-2 block", children: "\uD83D\uDCED" }), _jsx("p", { children: "No notifications" })] })) : (filteredNotifications.map((notification) => (_jsx("div", { className: `p-4 border-b border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors ${!notification.read ? 'bg-blue-50' : ''}`, onClick: () => markAsRead(notification.id), children: _jsxs("div", { className: "flex items-start space-x-3", children: [_jsx("span", { className: "text-lg flex-shrink-0", children: getTypeIcon(notification.type) }), _jsxs("div", { className: "flex-1 min-w-0", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("h4", { className: "text-sm font-medium text-slate-900 truncate", children: notification.title }), !notification.read && (_jsx("div", { className: "w-2 h-2 bg-blue-500 rounded-full flex-shrink-0" }))] }), _jsx("p", { className: "text-sm text-slate-600 mt-1", children: notification.message }), _jsx("p", { className: "text-xs text-slate-500 mt-2", children: notification.timestamp.toLocaleString() })] })] }) }, notification.id)))) }), filteredNotifications.length > 0 && (_jsx("div", { className: "p-3 border-t border-slate-200 text-center", children: _jsx("button", { onClick: () => setShowDropdown(false), className: "text-sm text-slate-600 hover:text-slate-900", children: "Close" }) }))] }))] }));
};
export default NotificationCenter;
