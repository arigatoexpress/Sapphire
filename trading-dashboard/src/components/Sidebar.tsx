import React, { useState, useEffect } from 'react';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  Avatar,
  Divider,
  IconButton,
  Chip,
  useMediaQuery,
  useTheme,
  Tooltip,
  Fade,
  Grow,
  Badge,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  AccountBalance as PortfolioIcon,
  Psychology as AgentsIcon,
  Analytics as AnalyticsIcon,
  Menu as MenuIcon,
  ChevronLeft as ChevronLeftIcon,
  Diamond as DiamondIcon,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTrading } from '../contexts/TradingContext';

const drawerWidth = 280;
const collapsedWidth = 72;

const Sidebar: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [collapsed, setCollapsed] = useState(() => {
    // Auto-collapse on smaller screens
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved ? JSON.parse(saved) : window.innerWidth < 1200;
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { portfolio, agentActivities } = useTrading();

  // Save collapsed state to localStorage
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', JSON.stringify(collapsed));
  }, [collapsed]);

  // Auto-collapse on window resize
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1200 && !collapsed) {
        setCollapsed(true);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [collapsed]);

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: <DashboardIcon />, description: 'System overview' },
    { path: '/portfolio', label: 'Portfolio', icon: <PortfolioIcon />, description: 'Asset allocation' },
    { path: '/agents', label: 'Agents', icon: <AgentsIcon />, description: 'AI trading agents' },
    { path: '/analytics', label: 'Analytics', icon: <AnalyticsIcon />, description: 'Performance data' },
  ];

  const handleDrawerToggle = () => {
    if (isMobile) {
      setMobileOpen(!mobileOpen);
    } else {
      setCollapsed(!collapsed);
    }
  };

  const handleNavigation = (path: string) => {
    navigate(path);
    if (isMobile) {
      setMobileOpen(false);
    }
  };

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box
        sx={{
          p: collapsed ? 2 : 3,
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          borderBottom: '1px solid',
          borderColor: 'divider',
          minHeight: 80,
          background: `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.action.hover} 100%)`,
          position: 'relative',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '1px',
            background: `linear-gradient(90deg, transparent, ${theme.palette.primary.main}, transparent)`,
          },
        }}
      >
        <Grow in={!collapsed} timeout={300}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Badge
              overlap="circular"
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              badgeContent={
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    bgcolor: 'success.main',
                    boxShadow: `0 0 8px ${theme.palette.success.main}`,
                  }}
                />
              }
            >
              <Avatar
                sx={{
                  bgcolor: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.primary.dark} 100%)`,
                  width: 40,
                  height: 40,
                  boxShadow: `0 4px 12px ${theme.palette.primary.main}30`,
                  border: `2px solid ${theme.palette.background.paper}`,
                }}
              >
                <DiamondIcon />
              </Avatar>
            </Badge>
            <Box>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  fontSize: '1.1rem',
                  lineHeight: 1.2,
                  background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                Sapphire
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  lineHeight: 1.2,
                  color: 'text.secondary',
                  fontWeight: 500,
                }}
              >
                Trade AI
              </Typography>
            </Box>
          </Box>
        </Grow>

        <Tooltip title={collapsed ? "Expand sidebar" : "Collapse sidebar"} placement="right">
          <IconButton
            onClick={handleDrawerToggle}
            sx={{
              color: 'text.secondary',
              transition: 'all 0.2s ease-in-out',
              '&:hover': {
                color: 'primary.main',
                bgcolor: 'action.hover',
                transform: 'scale(1.1)',
              },
              '&:active': {
                transform: 'scale(0.95)',
              },
            }}
          >
            {collapsed ? <MenuIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </Tooltip>
      </Box>

      {/* Quick Stats */}
      {!collapsed && (
        <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Typography variant="overline" sx={{ fontWeight: 600, color: 'text.secondary', mb: 1 }}>
            Quick Stats
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2" color="text.secondary">Portfolio</Typography>
              <Typography variant="body2" sx={{ fontWeight: 600, color: 'primary.main' }}>
                ${portfolio?.portfolio_value ? (portfolio.portfolio_value / 1000).toFixed(0) : '0'}K
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2" color="text.secondary">Active Agents</Typography>
              <Chip
                label={agentActivities.length}
                size="small"
                sx={{
                  height: 20,
                  fontSize: '0.7rem',
                  bgcolor: 'primary.main',
                  color: 'primary.contrastText',
                }}
              />
            </Box>
          </Box>
        </Box>
      )}

      {/* Navigation Menu */}
      <List sx={{ flexGrow: 1, pt: 2 }}>
        {menuItems.map((item) => {
          const isActive = location.pathname === item.path;
          const menuItem = (
            <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNavigation(item.path)}
                onMouseEnter={() => setHoveredItem(item.path)}
                onMouseLeave={() => setHoveredItem(null)}
                sx={{
                  mx: collapsed ? 1 : 2,
                  borderRadius: 2,
                  minHeight: collapsed ? 48 : 56,
                  px: collapsed ? 1 : 2,
                  position: 'relative',
                  '&::before': isActive ? {
                    content: '""',
                    position: 'absolute',
                    left: 0,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 4,
                    height: '60%',
                    bgcolor: 'primary.main',
                    borderRadius: '0 4px 4px 0',
                    boxShadow: `0 0 8px ${theme.palette.primary.main}50`,
                  } : {},
                  bgcolor: isActive ? 'rgba(0, 212, 170, 0.1)' : 'transparent',
                  border: isActive ? '1px solid rgba(0, 212, 170, 0.3)' : '1px solid transparent',
                  '&:hover': {
                    bgcolor: isActive ? 'rgba(0, 212, 170, 0.15)' : 'action.hover',
                    borderColor: isActive ? 'rgba(0, 212, 170, 0.4)' : 'rgba(0, 212, 170, 0.2)',
                    transform: 'translateX(2px)',
                  },
                  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                  '&:active': {
                    transform: 'translateX(1px) scale(0.98)',
                  },
                }}
              >
                <ListItemIcon
                  sx={{
                    color: isActive ? 'primary.main' : hoveredItem === item.path ? 'primary.light' : 'text.secondary',
                    minWidth: collapsed ? 'auto' : 40,
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                    transform: hoveredItem === item.path ? 'scale(1.1)' : 'scale(1)',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                {!collapsed && (
                  <Fade in={!collapsed} timeout={200}>
                    <ListItemText
                      primary={
                        <Typography
                          variant="body1"
                          sx={{
                            fontWeight: isActive ? 600 : 500,
                            color: isActive ? 'primary.main' : 'text.primary',
                            fontSize: '0.95rem',
                            transition: 'color 0.2s ease-in-out',
                          }}
                        >
                          {item.label}
                        </Typography>
                      }
                      secondary={
                        <Typography
                          variant="caption"
                          sx={{
                            color: hoveredItem === item.path ? 'text.primary' : 'text.secondary',
                            fontSize: '0.7rem',
                            lineHeight: 1.2,
                            transition: 'color 0.2s ease-in-out',
                          }}
                        >
                          {item.description}
                        </Typography>
                      }
                    />
                  </Fade>
                )}
              </ListItemButton>
            </ListItem>
          );

          return collapsed ? (
            <Tooltip
              key={item.path}
              title={
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {item.label}
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    {item.description}
                  </Typography>
                </Box>
              }
              placement="right"
              arrow
            >
              {menuItem}
            </Tooltip>
          ) : (
            menuItem
          );
        })}
      </List>

      {/* Footer */}
      <Divider
        sx={{
          mx: 2,
          my: 1,
          background: `linear-gradient(90deg, transparent, ${theme.palette.divider}, transparent)`,
        }}
      />
      <Box
        sx={{
          p: collapsed ? 2 : 3,
          textAlign: collapsed ? 'center' : 'left',
          background: `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.action.hover} 100%)`,
          position: 'relative',
          '&::before': {
            content: '""',
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: '1px',
            background: `linear-gradient(90deg, transparent, ${theme.palette.primary.main}, transparent)`,
          },
        }}
      >
        {!collapsed ? (
          <Fade in={!collapsed} timeout={300}>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <Box
                  sx={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    bgcolor: 'success.main',
                    animation: 'pulse 2s infinite',
                    '@keyframes pulse': {
                      '0%': { opacity: 1 },
                      '50%': { opacity: 0.5 },
                      '100%': { opacity: 1 },
                    },
                  }}
                />
                <Typography variant="caption" sx={{ fontWeight: 600, color: 'success.main', lineHeight: 1.4 }}>
                  System Online
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>
                Autonomous AI Trading
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ lineHeight: 1.4, opacity: 0.8 }}>
                Last updated: {new Date().toLocaleTimeString()}
              </Typography>
            </Box>
          </Fade>
        ) : (
          <Tooltip title="System Online - Autonomous AI Trading" placement="right">
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                bgcolor: 'success.main',
                mx: 'auto',
                boxShadow: '0 0 8px rgba(76, 175, 80, 0.5)',
                cursor: 'pointer',
                transition: 'all 0.2s ease-in-out',
                '&:hover': {
                  transform: 'scale(1.2)',
                  boxShadow: '0 0 12px rgba(76, 175, 80, 0.8)',
                },
              }}
            />
          </Tooltip>
        )}
      </Box>
    </Box>
  );

  const currentWidth = collapsed && !isMobile ? collapsedWidth : drawerWidth;

  return (
    <>
      {/* Mobile drawer */}
      {isMobile ? (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile
          }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
              bgcolor: 'background.paper',
              borderRight: '1px solid',
              borderColor: 'divider',
            },
          }}
        >
          {drawer}
        </Drawer>
      ) : (
        /* Desktop drawer */
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: currentWidth,
              bgcolor: 'background.paper',
              borderRight: '1px solid',
              borderColor: 'divider',
              transition: theme.transitions.create('width', {
                easing: theme.transitions.easing.sharp,
                duration: theme.transitions.duration.leavingScreen,
              }),
              overflowX: 'hidden',
            },
          }}
        >
          {drawer}
        </Drawer>
      )}
    </>
  );
};

export default Sidebar;
