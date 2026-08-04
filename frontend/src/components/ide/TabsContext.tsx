'use client';

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { TabType } from '../../types';

interface TabsContextValue {
  openTabs: TabType[];
  activeTab: TabType;
  openTab: (tab: TabType) => void;
  closeTab: (tab: TabType) => void;
  setActiveTab: (tab: TabType) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

/** VSCode-style tab model: each TabType is a singleton view, either open or
 * closed -- opening an already-open tab just focuses it, mirroring how the
 * Explorer/Activity Bar can't spawn a second "Fleet Registry" tab since the
 * view itself has no per-instance identity (it re-fetches its own data on
 * mount, same as before this rebuild). At least one tab always stays open so
 * the editor area is never empty. */
export const TabsProvider: React.FC<{ initialTab: TabType; children: React.ReactNode }> = ({
  initialTab,
  children,
}) => {
  const [openTabs, setOpenTabs] = useState<TabType[]>([initialTab]);
  const [activeTab, setActiveTabState] = useState<TabType>(initialTab);

  const openTab = useCallback((tab: TabType) => {
    setOpenTabs((prev) => (prev.includes(tab) ? prev : [...prev, tab]));
    setActiveTabState(tab);
  }, []);

  const closeTab = useCallback((tab: TabType) => {
    setOpenTabs((prev) => {
      if (prev.length <= 1) return prev; // keep at least one tab open
      const idx = prev.indexOf(tab);
      if (idx === -1) return prev;
      const next = prev.filter((t) => t !== tab);
      setActiveTabState((current) => {
        if (current !== tab) return current;
        // Focus the tab that was to its left, VSCode-style.
        return next[Math.max(0, idx - 1)];
      });
      return next;
    });
  }, []);

  const setActiveTab = useCallback((tab: TabType) => {
    setOpenTabs((prev) => (prev.includes(tab) ? prev : [...prev, tab]));
    setActiveTabState(tab);
  }, []);

  const value = useMemo(
    () => ({ openTabs, activeTab, openTab, closeTab, setActiveTab }),
    [openTabs, activeTab, openTab, closeTab, setActiveTab]
  );

  return <TabsContext.Provider value={value}>{children}</TabsContext.Provider>;
};

export function useTabs(): TabsContextValue {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('useTabs() must be used inside a <TabsProvider>');
  return ctx;
}
