import 'server-only';

import { eq } from 'drizzle-orm';
import { db } from './drizzle';
import { users, teams, teamMembers, type User, type TeamDataWithMembers } from './schema';
import { cookies } from 'next/headers';
import { jwtVerify } from 'jose';

const key = new TextEncoder().encode(process.env.AUTH_SECRET);

/**
 * Retrieve the current authenticated user from the session cookie.
 * Returns null when there is no valid session.
 */
export async function getUser(): Promise<User | null> {
    const sessionCookie = (await cookies()).get('session')?.value;
    if (!sessionCookie) return null;

    try {
        const { payload } = await jwtVerify(sessionCookie, key, {
            algorithms: ['HS256'],
        });

        const userId = (payload as { user?: { id: number } }).user?.id;
        if (!userId) return null;

        const [user] = await db
            .select()
            .from(users)
            .where(eq(users.id, userId))
            .limit(1);

        return user ?? null;
    } catch {
        return null;
    }
}

/**
 * Get the user together with their team membership info.
 */
export async function getUserWithTeam(userId: number) {
    const [row] = await db
        .select({
            id: users.id,
            name: users.name,
            email: users.email,
            passwordHash: users.passwordHash,
            role: users.role,
            createdAt: users.createdAt,
            updatedAt: users.updatedAt,
            deletedAt: users.deletedAt,
            teamId: teamMembers.teamId,
        })
        .from(users)
        .leftJoin(teamMembers, eq(users.id, teamMembers.userId))
        .where(eq(users.id, userId))
        .limit(1);

    return row ?? null;
}

/**
 * Get team data with members for the currently authenticated user.
 */
export async function getTeamForUser(): Promise<TeamDataWithMembers | null> {
    const user = await getUser();
    if (!user) return null;

    const membership = await db
        .select()
        .from(teamMembers)
        .where(eq(teamMembers.userId, user.id))
        .limit(1);

    if (membership.length === 0) return null;

    const [team] = await db
        .select()
        .from(teams)
        .where(eq(teams.id, membership[0].teamId))
        .limit(1);

    if (!team) return null;

    const members = await db
        .select({
            id: teamMembers.id,
            userId: teamMembers.userId,
            teamId: teamMembers.teamId,
            role: teamMembers.role,
            joinedAt: teamMembers.joinedAt,
            user: {
                id: users.id,
                name: users.name,
                email: users.email,
            },
        })
        .from(teamMembers)
        .leftJoin(users, eq(teamMembers.userId, users.id))
        .where(eq(teamMembers.teamId, team.id));

    return {
        ...team,
        teamMembers: members as TeamDataWithMembers['teamMembers'],
    };
}
