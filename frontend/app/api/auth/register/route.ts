import { NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { hashPassword, generateToken } from '@/lib/auth';

export async function POST(request: Request) {
  try {
    const { name, email, password } = await request.json();

    if (!name || !email || !password) {
      return NextResponse.json(
        { error: 'Name, email, and password are required' },
        { status: 400 }
      );
    }

    if (password.length < 6) {
      return NextResponse.json(
        { error: 'Password must be at least 6 characters long' },
        { status: 400 }
      );
    }

    const existingUsers = await query(
      `SELECT id FROM "User" WHERE LOWER(email) = LOWER($1) LIMIT 1;`,
      [email]
    );

    if (existingUsers.length > 0) {
      return NextResponse.json(
        { error: 'An account with this email address already exists' },
        { status: 409 }
      );
    }

    const hashedPassword = await hashPassword(password);
    const now = new Date().toISOString();

    const newUsers = await query(
      `INSERT INTO "User" (name, email, "passwordHash", "createdAt") 
       VALUES ($1, $2, $3, $4) 
       RETURNING id, name, email, "createdAt";`,
      [name, email, hashedPassword, now]
    );

    const user = newUsers[0];

    const token = generateToken({
      userId: user.id,
      email: user.email,
      name: user.name,
    });

    const response = NextResponse.json(
      {
        message: 'Account created successfully',
        user: {
          id: user.id,
          name: user.name,
          email: user.email,
        },
        token,
      },
      { status: 201 }
    );

    response.cookies.set('auth_token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 7 * 24 * 60 * 60,
      path: '/',
    });

    return response;
  } catch (error: any) {
    console.error('Registration API Error:', error);
    return NextResponse.json(
      { error: error.message || 'Server error during registration' },
      { status: 500 }
    );
  }
}
