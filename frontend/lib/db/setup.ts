import { exec } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { promisify } from 'node:util';
import readline from 'node:readline';
import crypto from 'node:crypto';
import path from 'node:path';

const execAsync = promisify(exec);

function question(query: string): Promise<string> {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    return new Promise((resolve) =>
        rl.question(query, (ans) => {
            rl.close();
            resolve(ans);
        })
    );
}


async function getPostgresURL(): Promise<string> {
    console.log('Step 2: Setting up Postgres');
    const dbChoice = await question(
        'Do you want to use a local Postgres instance with Docker (L) or a remote Postgres instance (R)? (L/R): '
    );

    if (dbChoice.toLowerCase() === 'l') {
        console.log('Setting up local Postgres instance with Docker...');
        await setupLocalPostgres();
        return 'postgres://postgres:postgres@localhost:54322/postgres';
    } else {
        console.log(
            'You can find Postgres databases at: https://vercel.com/marketplace?category=databases'
        );
        return await question('Enter your POSTGRES_URL: ');
    }
}

async function setupLocalPostgres() {
    console.log('Assuming local Postgres is managed via root docker-compose.yaml...');
    console.log('If it is not running, please run `make up` from the project root.');
}


function generateAuthSecret(): string {
    console.log('Step 3: Generating AUTH_SECRET...');
    return crypto.randomBytes(32).toString('hex');
}

async function writeEnvFile(envVars: Record<string, string>) {
    console.log('Step 4: Writing environment variables to .env');
    const envContent = Object.entries(envVars)
        .map(([key, value]) => `${key}=${value}`)
        .join('\n');

    await fs.writeFile(path.join(process.cwd(), '.env'), envContent);
    console.log('.env file created with the necessary variables.');
}

async function main() {
    const POSTGRES_URL = await getPostgresURL();
    const BASE_URL = 'http://localhost:3000';
    const BACKEND_URL = 'http://localhost:8000';
    const AUTH_SECRET = generateAuthSecret();

    await writeEnvFile({
        POSTGRES_URL,
        BASE_URL,
        BACKEND_URL,
        AUTH_SECRET,
    });

    console.log('🎉 Setup completed successfully!');
}

main().catch(console.error);
