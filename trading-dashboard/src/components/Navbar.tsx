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
  useMediaQuery,
  useTheme,
  Chip,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  AccountBalance as PortfolioIcon,
  Psychology as AgentsIcon,
  Analytics as AnalyticsIcon,
  Settings as SettingsIcon,
  AccountCircle,
  Menu as MenuIcon,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTrading } from '../contexts/TradingContext';

const Navbar: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();
  const { portfolio } = useTrading();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  // No authentication needed - public access

  const navItems = [
    { path: '/', label: 'Dashboard', icon: <DashboardIcon />, description: 'System overview' },
    { path: '/portfolio', label: 'Portfolio', icon: <PortfolioIcon />, description: 'Asset allocation' },
    { path: '/agents', label: 'Agents', icon: <AgentsIcon />, description: 'AI trading agents' },
    { path: '/analytics', label: 'Analytics', icon: <AnalyticsIcon />, description: 'Performance data' },
    { path: '/settings', label: 'Settings', icon: <SettingsIcon />, description: 'System configuration' },
  ];

  const handleMobileMenuToggle = () => {
    setMobileMenuOpen(!mobileMenuOpen);
  };

  const handleMobileNavigation = (path: string) => {
    navigate(path);
    setMobileMenuOpen(false);
  };

  return (
    <>
      <AppBar
        position="static"
        sx={{
          background: 'linear-gradient(90deg, #1a1a1a 0%, #2a2a2a 100%)',
          boxShadow: '0 2px 10px rgba(0,0,0,0.3)',
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 56, md: 64 } }}>
          {/* Mobile Menu Button */}
          {isMobile && (
            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={handleMobileMenuToggle}
              sx={{ mr: 2 }}
            >
              <MenuIcon />
            </IconButton>
          )}

          {/* Logo */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography
              variant="h6"
              component="div"
              sx={{
                flexGrow: { xs: 1, md: 0 },
                fontWeight: 700,
                fontSize: { xs: '1.1rem', md: '1.25rem' },
                background: 'linear-gradient(45deg, #00d4aa 30%, #00f5d4 90%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              💎 Sapphire Trade ✨
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, alignItems: 'flex-start' }}>
              <Chip
                label="🏆 Vibe Coding Competition Entry"
                size="small"
                sx={{
                  bgcolor: 'rgba(255, 215, 0, 0.2)',
                  color: '#ffd700',
                  border: '1px solid #ffd700',
                  fontWeight: 700,
                  fontSize: '0.65rem',
                  height: '18px',
                  '& .MuiChip-label': {
                    px: 1,
                  },
                }}
              />
              <Chip
                label="🚀 Built on Aster DEX"
                size="small"
                sx={{
                  bgcolor: 'rgba(138, 43, 226, 0.2)',
                  color: '#8a2be2',
                  border: '1px solid #8a2be2',
                  fontWeight: 600,
                  fontSize: '0.7rem',
                  height: '20px',
                  '& .MuiChip-label': {
                    px: 1,
                  },
                }}
              />
            </Box>
          </Box>

          {/* Desktop Navigation */}
          {!isMobile && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexGrow: 1 }}>
              {/* Portfolio Value Chip */}
              {portfolio && (
                <Chip
                  label={`$${portfolio.portfolio_value.toLocaleString()}`}
                  variant="outlined"
                  sx={{
                    color: '#00d4aa',
                    borderColor: '#00d4aa',
                    fontWeight: 600,
                    mr: 2,
                  }}
                />
              )}

              {/* Navigation Buttons */}
              {navItems.map((item) => (
                <Button
                  key={item.path}
                  color="inherit"
                  onClick={() => navigate(item.path)}
                  sx={{
                    color: location.pathname === item.path ? '#00d4aa' : 'white',
                    fontWeight: location.pathname === item.path ? 600 : 400,
                    fontSize: '0.9rem',
                    px: 2,
                    py: 1,
                    borderRadius: 2,
                    '&:hover': {
                      color: '#00f5d4',
                      bgcolor: 'rgba(0, 212, 170, 0.1)',
                    },
                  }}
                  startIcon={item.icon}
                >
                  {item.label}
                </Button>
              ))}
            </Box>
          )}

          {/* User Menu */}
          <IconButton
            size="large"
            aria-label="account of current user"
            aria-controls="menu-appbar"
            aria-haspopup="true"
            onClick={handleMenu}
            color="inherit"
            sx={{ ml: { xs: 0, md: 2 } }}
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

        {/* Mobile Navigation Menu */}
        {isMobile && mobileMenuOpen && (
          <Box
            sx={{
              bgcolor: 'background.paper',
              borderTop: '1px solid',
              borderColor: 'divider',
              px: 2,
              py: 1,
            }}
          >
            {/* Mobile Portfolio Value */}
            {portfolio && (
              <Box sx={{ mb: 2, textAlign: 'center' }}>
                <Chip
                  label={`Portfolio: $${portfolio.portfolio_value.toLocaleString()}`}
                  sx={{
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    fontWeight: 600,
                    fontSize: '0.9rem',
                  }}
                />
              </Box>
            )}

            {/* Mobile Navigation Items */}
            {navItems.map((item) => (
              <Button
                key={item.path}
                fullWidth
                onClick={() => handleMobileNavigation(item.path)}
                sx={{
                  justifyContent: 'flex-start',
                  color: location.pathname === item.path ? 'primary.main' : 'text.primary',
                  fontWeight: location.pathname === item.path ? 600 : 400,
                  py: 1.5,
                  mb: 0.5,
                  borderRadius: 2,
                  bgcolor: location.pathname === item.path ? 'rgba(0, 212, 170, 0.1)' : 'transparent',
                  '&:hover': {
                    bgcolor: 'action.hover',
                  },
                }}
                startIcon={item.icon}
              >
                <Box sx={{ textAlign: 'left' }}>
                  <Typography variant="body1" sx={{ fontSize: '1rem' }}>
                    {item.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
                    {item.description}
                  </Typography>
                </Box>
              </Button>
            ))}
          </Box>
        )}
      </AppBar>
    </>
  );
};

export default Navbar;
