'use client';

import { useActionState } from 'react';
import { updateAccount, updatePassword, deleteAccount } from '@/app/(login)/actions';
import type { ActionState } from '@/lib/auth/middleware';

export default function SettingsPage() {
    const [accountState, accountAction, accountPending] = useActionState<ActionState, FormData>(
        updateAccount,
        {}
    );
    const [passwordState, passwordAction, passwordPending] = useActionState<ActionState, FormData>(
        updatePassword,
        {}
    );
    const [deleteState, deleteAction, deletePending] = useActionState<ActionState, FormData>(
        deleteAccount,
        {}
    );

    return (
        <div className="max-w-2xl mx-auto px-4 py-8 space-y-10">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
                <p className="text-muted-foreground mt-1">
                    Manage your account and security preferences.
                </p>
            </div>

            {/* ── General ──────────────────────────────────────────── */}
            <section className="rounded-xl border border-border bg-card p-6 space-y-5">
                <div>
                    <h2 className="text-lg font-semibold">General</h2>
                    <p className="text-sm text-muted-foreground">Update your name and email address.</p>
                </div>

                <form action={accountAction} className="space-y-4">
                    <div className="space-y-1.5">
                        <label htmlFor="settings-name" className="text-sm font-medium">
                            Name
                        </label>
                        <input
                            id="settings-name"
                            name="name"
                            type="text"
                            required
                            defaultValue={accountState.name ?? ''}
                            placeholder="Your name"
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>

                    <div className="space-y-1.5">
                        <label htmlFor="settings-email" className="text-sm font-medium">
                            Email
                        </label>
                        <input
                            id="settings-email"
                            name="email"
                            type="email"
                            required
                            defaultValue={accountState.email ?? ''}
                            placeholder="you@example.com"
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>

                    {accountState.success && (
                        <p className="text-sm text-green-600">{accountState.success}</p>
                    )}
                    {accountState.error && (
                        <p className="text-sm text-destructive">{accountState.error}</p>
                    )}

                    <button
                        type="submit"
                        disabled={accountPending}
                        className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer"
                    >
                        {accountPending ? 'Saving…' : 'Save Changes'}
                    </button>
                </form>
            </section>

            {/* ── Security ─────────────────────────────────────────── */}
            <section className="rounded-xl border border-border bg-card p-6 space-y-5">
                <div>
                    <h2 className="text-lg font-semibold">Security</h2>
                    <p className="text-sm text-muted-foreground">Change your password.</p>
                </div>

                <form action={passwordAction} className="space-y-4">
                    <div className="space-y-1.5">
                        <label htmlFor="settings-current-password" className="text-sm font-medium">
                            Current Password
                        </label>
                        <input
                            id="settings-current-password"
                            name="currentPassword"
                            type="password"
                            required
                            minLength={8}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>

                    <div className="space-y-1.5">
                        <label htmlFor="settings-new-password" className="text-sm font-medium">
                            New Password
                        </label>
                        <input
                            id="settings-new-password"
                            name="newPassword"
                            type="password"
                            required
                            minLength={8}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>

                    <div className="space-y-1.5">
                        <label htmlFor="settings-confirm-password" className="text-sm font-medium">
                            Confirm New Password
                        </label>
                        <input
                            id="settings-confirm-password"
                            name="confirmPassword"
                            type="password"
                            required
                            minLength={8}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>

                    {passwordState.success && (
                        <p className="text-sm text-green-600">{passwordState.success}</p>
                    )}
                    {passwordState.error && (
                        <p className="text-sm text-destructive">{passwordState.error}</p>
                    )}

                    <button
                        type="submit"
                        disabled={passwordPending}
                        className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer"
                    >
                        {passwordPending ? 'Updating…' : 'Update Password'}
                    </button>
                </form>
            </section>

            {/* ── Danger Zone ──────────────────────────────────────── */}
            <section className="rounded-xl border border-destructive/30 bg-card p-6 space-y-5">
                <div>
                    <h2 className="text-lg font-semibold text-destructive">Danger Zone</h2>
                    <p className="text-sm text-muted-foreground">
                        Permanently delete your account. This action cannot be undone.
                    </p>
                </div>

                <form action={deleteAction} className="space-y-4">
                    <div className="space-y-1.5">
                        <label htmlFor="settings-delete-password" className="text-sm font-medium">
                            Confirm Password
                        </label>
                        <input
                            id="settings-delete-password"
                            name="password"
                            type="password"
                            required
                            minLength={8}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>

                    {deleteState.error && (
                        <p className="text-sm text-destructive">{deleteState.error}</p>
                    )}

                    <button
                        type="submit"
                        disabled={deletePending}
                        className="inline-flex items-center justify-center rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 transition-colors cursor-pointer"
                    >
                        {deletePending ? 'Deleting…' : 'Delete Account'}
                    </button>
                </form>
            </section>
        </div>
    );
}
