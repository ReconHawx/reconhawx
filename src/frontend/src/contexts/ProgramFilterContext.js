import React, { createContext, useContext, useState, useEffect } from 'react';
import { programAPI } from '../services/api';
import { useAuth } from './AuthContext';

export const ProgramFilterContext = createContext();

export const useProgramFilter = () => {
  const context = useContext(ProgramFilterContext);
  if (!context) {
    throw new Error('useProgramFilter must be used within a ProgramFilterProvider');
  }
  return context;
};

export const ProgramFilterProvider = ({ children }) => {
  const [selectedProgram, setSelectedProgram] = useState('');
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(false);
  const { user } = useAuth();

  // Load programs only when user is authenticated
  useEffect(() => {
    if (user && user.username) {
      loadPrograms();
    } else {
      // Clear programs when user is not authenticated
      setPrograms([]);
      setSelectedProgram('');
    }
  }, [user]);

  // Load stored program filter from localStorage on mount
  useEffect(() => {
    const storedProgram = localStorage.getItem('global_program_filter');
    if (storedProgram) {
      setSelectedProgram(storedProgram);
    }
  }, []);

  // Save to localStorage when program changes
  useEffect(() => {
    if (selectedProgram) {
      localStorage.setItem('global_program_filter', selectedProgram);
    } else {
      localStorage.removeItem('global_program_filter');
    }
  }, [selectedProgram]);

  const loadPrograms = async () => {
    try {
      setLoading(true);
      
      // Use the authenticated getAll endpoint which handles user filtering
      const response = await programAPI.getAll();
      
      // Backend now handles program filtering based on user permissions
      // Use programs_with_permissions to get full program data including protected_domains
      if (response.status === 'success' && response.programs_with_permissions) {
        setPrograms(response.programs_with_permissions);
      } else if (response.status === 'success' && response.programs) {
        // Fallback: convert array of names to objects
        setPrograms(response.programs.map(name => ({ name })));
      } else if (response.items && Array.isArray(response.items)) {
        // Handle case where response has items array (like from query API)
        setPrograms(response.items);
      } else if (Array.isArray(response)) {
        // Handle case where response is directly an array
        setPrograms(response);
      } else {
        setPrograms([]);
      }
    } catch (error) {
      console.error('Failed to load programs:', error);
      setPrograms([]);
    } finally {
      setLoading(false);
    }
  };

  const clearFilter = () => {
    setSelectedProgram('');
  };

  const value = {
    selectedProgram,
    setSelectedProgram,
    programs,
    loading,
    clearFilter,
    refreshPrograms: loadPrograms
  };

  return (
    <ProgramFilterContext.Provider value={value}>
      {children}
    </ProgramFilterContext.Provider>
  );
};