import React from 'react';
import { Button } from 'react-bootstrap';
import { useTheme } from '../contexts/ThemeContext';

function ThemeToggle({ size = 'sm', variant = 'outline-secondary' }) {
  const { theme, toggleTheme, isLoading } = useTheme();

  if (isLoading) {
    return null; // Don't render until theme is loaded
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={toggleTheme}
      title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      className="theme-toggle"
    >
      {theme === 'light' ? '🌙' : '☀️'}
    </Button>
  );
}

export default ThemeToggle;