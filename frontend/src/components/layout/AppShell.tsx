'use client'

import { useState } from 'react'
import { Menu } from 'lucide-react'
import { AppSidebar, LogoPebbles } from './AppSidebar'
import { SetupBanner } from './SetupBanner'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const { t } = useTranslation()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden h-full shrink-0 md:block">
        <AppSidebar />
      </div>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 md:hidden" data-testid="mobile-navigation">
          <button
            type="button"
            aria-label={t('common.close')}
            className="absolute inset-0 bg-ink/35 backdrop-blur-[2px]"
            onClick={() => setMobileNavOpen(false)}
          />
          <div className="relative h-full w-64 max-w-[85vw] shadow-2xl">
            <AppSidebar mobile onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </div>
      )}

      <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-3 md:hidden">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={t('navigation.nav')}
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <LogoPebbles />
          <span className="font-display text-sm font-bold tracking-tight">
            {t('common.appName')}
          </span>
        </div>
        <SetupBanner />
        {children}
      </main>
    </div>
  )
}
