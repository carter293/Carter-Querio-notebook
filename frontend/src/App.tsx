import { SignedIn, SignedOut, RedirectToSignIn, useAuth } from '@clerk/clerk-react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { NotebookApp } from './components/NotebookApp';
import { setupAuthInterceptor } from './api-client';
import { useEffect } from 'react';

export default function App() {
  const { getToken, isLoaded } = useAuth();

  useEffect(() => {
    // Wait for Clerk to load before setting up interceptor
    if (!isLoaded) {
      return;
    }

    // Setup interceptor once Clerk is ready
    const cleanup = setupAuthInterceptor(getToken);
    
    // Cleanup on unmount (important for React Strict Mode)
    return cleanup;
  }, [getToken, isLoaded]);

  // Show loading state while Clerk initializes
  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground dark">
        <div className="text-center">
          <div className="mb-4 text-xl">Loading authentication...</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <SignedIn>
        <Routes>
          <Route path="/notebook/:notebookId" element={<NotebookApp />} />
          <Route path="/" element={<NotebookApp />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </>
  );
}
