import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'

vi.mock('./AppSidebar', () => ({
  LogoPebbles: () => <span data-testid="logo-pebbles" />,
  AppSidebar: ({ mobile }: { mobile?: boolean }) => (
    <div data-testid={mobile ? 'mobile-sidebar' : 'desktop-sidebar'} />
  ),
}))

vi.mock('./SetupBanner', () => ({
  SetupBanner: () => null,
}))

describe('AppShell', () => {
  it('keeps desktop navigation out of the mobile layout and opens an overlay menu', () => {
    render(<AppShell><div>workspace</div></AppShell>)

    expect(screen.getByTestId('desktop-sidebar').parentElement?.className).toContain('hidden')
    expect(screen.queryByTestId('mobile-navigation')).toBeNull()
    expect(screen.getByText('workspace')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'navigation.nav' }))

    expect(screen.getByTestId('mobile-navigation')).toBeDefined()
    expect(screen.getByTestId('mobile-sidebar')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'common.close' }))
    expect(screen.queryByTestId('mobile-navigation')).toBeNull()
  })
})
