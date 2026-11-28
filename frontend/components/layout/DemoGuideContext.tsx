'use client';

import React, { createContext, useContext, useState } from 'react';

interface DemoGuideContextValue {
  demoGuide: boolean;
  toggleDemoGuide: () => void;
}

const DemoGuideContext = createContext<DemoGuideContextValue>({
  demoGuide: false,
  toggleDemoGuide: () => {},
});

export function DemoGuideProvider({ children }: { children: React.ReactNode }) {
  const [demoGuide, setDemoGuide] = useState(false);

  const toggleDemoGuide = () => setDemoGuide((prev) => !prev);

  return (
    <DemoGuideContext.Provider value={{ demoGuide, toggleDemoGuide }}>
      {children}
    </DemoGuideContext.Provider>
  );
}

export function useDemoGuide() {
  return useContext(DemoGuideContext);
}
