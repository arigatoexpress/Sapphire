import React, { useState } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  IconButton,
  Menu,
  MenuItem,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  useTheme,
  Chip,
  Avatar,
  Fade,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  AccountBalance as PortfolioIcon,
  Psychology as AgentsIcon,
  Analytics as AnalyticsIcon,
  RocketLaunch as MissionControlIcon,
  Settings as SettingsIcon,
  AccountCircle,
  Menu as MenuIcon,
  Diamond as DiamondIcon,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTrading } from '../contexts/TradingContext';
import EasterEgg from './EasterEgg';

const drawerWidth = 280;

const Navbar: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const { portfolio, agentActivities } = useTrading();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [logoClickCount, setLogoClickCount] = useState(0);
  const [showEasterEgg, setShowEasterEgg] = useState(false);

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const navItems = [
    { path: '/', label: 'AI Network', icon: <AnalyticsIcon />, description: 'Neural network visualization' },
    { path: '/dashboard', label: 'Dashboard', icon: <DashboardIcon />, description: 'System overview' },
    { path: '/portfolio', label: 'Portfolio', icon: <PortfolioIcon />, description: 'Asset allocation' },
    { path: '/agents', label: 'Agents', icon: <AgentsIcon />, description: 'AI trading agents' },
    { path: '/mission-control', label: 'Mission Control', icon: <MissionControlIcon />, description: 'Infrastructure & metrics' },
  ];

  const handleDrawerToggle = () => {
    setDrawerOpen(!drawerOpen);
  };

  const handleNavigation = (path: string) => {
    navigate(path);
    setDrawerOpen(false);
  };

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Drawer Header */}
      <Box
        sx={{
          p: 3,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          borderBottom: '1px solid',
          borderColor: 'divider',
          background: `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.action.hover} 100%)`,
        }}
      >
        <Avatar
          sx={{
            bgcolor: 'primary.main',
            width: 48,
            height: 48,
            boxShadow: `0 4px 12px ${theme.palette.primary.main}30`,
          }}
        >
          <DiamondIcon />
        </Avatar>
        <Box>
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              fontSize: '1.1rem',
              background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            Sapphire Trade
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
            AI Trading System
          </Typography>
        </Box>
      </Box>

      {/* Portfolio Stats */}
      {portfolio && (
        <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Typography variant="overline" sx={{ fontWeight: 600, color: 'text.secondary', mb: 1, display: 'block' }}>
            Portfolio
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="body2" color="text.secondary">Bot Trading Capital</Typography>
            <Typography variant="body2" sx={{ fontWeight: 600, color: 'primary.main' }}>
              ${portfolio?.agent_allocations ? Object.values(portfolio.agent_allocations).reduce((sum: number, val: any) => sum + (val || 0), 0).toLocaleString() : '3,000'}
            </Typography>
          </Box>
          {agentActivities && (
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
          )}
        </Box>
      )}

      {/* Navigation Menu */}
      <List sx={{ flexGrow: 1, pt: 2 }}>
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNavigation(item.path)}
                sx={{
                  mx: 2,
                  borderRadius: 2,
                  minHeight: 56,
                  px: 2,
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
                }}
              >
                <ListItemIcon
                  sx={{
                    color: isActive ? 'primary.main' : 'text.secondary',
                    minWidth: 40,
                    transition: 'color 0.2s ease-in-out',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Typography
                      variant="body1"
                      sx={{
                        fontWeight: isActive ? 600 : 500,
                        color: isActive ? 'primary.main' : 'text.primary',
                        fontSize: '0.95rem',
                      }}
                    >
                      {item.label}
                    </Typography>
                  }
                  secondary={
                    <Typography
                      variant="caption"
                      sx={{
                        color: 'text.secondary',
                        fontSize: '0.7rem',
                      }}
                    >
                      {item.description}
                    </Typography>
                  }
                />
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>

      {/* Drawer Footer */}
      <Divider sx={{ mx: 2 }} />
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mb: 0.5 }}>
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              bgcolor: 'success.main',
              boxShadow: '0 0 8px rgba(76, 175, 80, 0.5)',
            }}
          />
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'success.main' }}>
            System Online
          </Typography>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
          Autonomous AI Trading
        </Typography>
      </Box>
    </Box>
  );

  return (
    <>
      <EasterEgg trigger={showEasterEgg} onClose={() => setShowEasterEgg(false)} />
      <AppBar
        position="static"
        sx={{
          background: 'linear-gradient(90deg, #1a1a1a 0%, #2a2a2a 100%)',
          boxShadow: '0 2px 10px rgba(0,0,0,0.3)',
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 56, md: 64 } }}>
          {/* Hamburger Menu Button - Always Visible */}
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2 }}
          >
            <MenuIcon />
          </IconButton>

          {/* Logo */}
          <Box 
            sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 1, 
              flexGrow: 1,
              cursor: 'pointer',
              '&:hover': {
                opacity: 0.8,
              },
              transition: 'opacity 0.2s ease',
            }}
            onClick={() => {
              const newCount = logoClickCount + 1;
              setLogoClickCount(newCount);
              if (newCount >= 5) {
                setShowEasterEgg(true);
                setLogoClickCount(0);
              }
            }}
          >
            <Typography
              variant="h6"
              component="div"
              sx={{
                fontWeight: 700,
                fontSize: { xs: '1rem', sm: '1.1rem', md: '1.25rem' },
                background: 'linear-gradient(45deg, #00d4aa 30%, #00f5d4 90%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              💎 Sapphire Trade
            </Typography>
            <Box sx={{ display: { xs: 'none', sm: 'flex' }, flexDirection: 'column', gap: 0.5, alignItems: 'flex-start' }}>
              <Chip
                label="🏆 Competition Entry"
                size="small"
                sx={{
                  bgcolor: 'rgba(255, 215, 0, 0.2)',
                  color: '#ffd700',
                  border: '1px solid #ffd700',
                  fontWeight: 700,
                  fontSize: '0.6rem',
                  height: '18px',
                  '& .MuiChip-label': {
                    px: 0.75,
                  },
                }}
              />
              <Chip
                label="🚀 Aster DEX"
                size="small"
                sx={{
                  bgcolor: 'rgba(138, 43, 226, 0.2)',
                  color: '#8a2be2',
                  border: '1px solid #8a2be2',
                  fontWeight: 600,
                  fontSize: '0.65rem',
                  height: '18px',
                  '& .MuiChip-label': {
                    px: 0.75,
                  },
                }}
              />
            </Box>
          </Box>

          {/* Bot Trading Capital Chip */}
          {portfolio && (
            <Chip
              label={`$${(portfolio?.agent_allocations ? Object.values(portfolio.agent_allocations).reduce((sum: number, val: any) => sum + (val || 0), 0) : 3000).toLocaleString()}`}
              variant="outlined"
              sx={{
                color: '#00d4aa',
                borderColor: '#00d4aa',
                fontWeight: 600,
                mr: 2,
              }}
            />
          )}

          {/* User Menu */}
          <IconButton
            size="large"
            aria-label="account of current user"
            aria-controls="menu-appbar"
            aria-haspopup="true"
            onClick={handleMenu}
            color="inherit"
          >
            <AccountCircle />
          </IconButton>
          <Menu
            id="menu-appbar"
            anchorEl={anchorEl}
            anchorOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
            keepMounted
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
            open={Boolean(anchorEl)}
            onClose={handleClose}
            sx={{
              '& .MuiPaper-root': {
                bgcolor: 'background.paper',
                border: '1px solid',
                borderColor: 'divider',
              }
            }}
          >
            <MenuItem disabled sx={{ opacity: 0.7 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Public Access
              </Typography>
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      {/* Drawer Menu - Always Available */}
      <Drawer
        anchor="left"
        open={drawerOpen}
        onClose={handleDrawerToggle}
        sx={{
          '& .MuiDrawer-paper': {
            boxSizing: 'border-box',
            width: drawerWidth,
            bgcolor: 'background.paper',
            borderRight: '1px solid',
            borderColor: 'divider',
          },
        }}
        ModalProps={{
          keepMounted: true, // Better open performance
        }}
      >
        {drawer}
      </Drawer>
    </>
  );
};

export default Navbar;
