import { Pool, neon } from '@neondatabase/serverless';

const connectionString = process.env.DATABASE_URL || "postgresql://neondb_owner:npg_fQGVYh90qgZX@ep-tiny-meadow-b3qqap6m-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require";

export const pool = new Pool({ connectionString });
export const sql = neon(connectionString);

export async function query(text: string, params: any[] = []) {
  try {
    const res = await pool.query(text, params);
    return res.rows;
  } catch (error) {
    console.error('Neon DB Error:', error);
    throw error;
  }
}
