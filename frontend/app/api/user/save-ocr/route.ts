import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { verifyToken } from '@/lib/auth';
import { query } from '@/lib/db';

export async function POST(request: Request) {
  try {
    const cookieStore = await cookies();
    let token = cookieStore.get('auth_token')?.value;

    if (!token) {
      const authHeader = request.headers.get('authorization');
      if (authHeader && authHeader.startsWith('Bearer ')) {
        token = authHeader.substring(7);
      }
    }

    if (!token) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const payload = verifyToken(token);
    if (!payload) {
      return NextResponse.json({ error: 'Invalid token' }, { status: 401 });
    }

    const { filename, ocrResults } = await request.json();

    const now = new Date().toISOString();

    // 1. Insert Document record in Neon DB for this user
    const newDocs = await query(
      `INSERT INTO "Document" ("userId", "originalName", "storedFilename", "documentType", "mimeType", "filePath", "status", "uploadedAt")
       VALUES ($1, $2, $3, 'PRESCRIPTION', 'image/jpeg', $4, 'CONFIRMED', $5)
       RETURNING id;`,
      [payload.userId, filename || 'scanned_prescription.jpg', filename || 'scanned_prescription.jpg', '/uploads/' + filename, now]
    );

    const docId = newDocs[0].id;

    // Build structured medicines array from OCR detected text lines
    const detectedMedicines = ocrResults?.results ? ocrResults.results.map((r: any) => ({
      name: r.text,
      confidence: r.confidence,
    })) : [];

    const summaryText = `Prescription document uploaded by ${payload.name}. Extracted ${detectedMedicines.length} text items via PaddleOCR.`;

    // 2. Insert Analysis record in Neon DB
    await query(
      `INSERT INTO "Analysis" ("documentId", "summary", "structuredResult", "isDemo", "createdAt")
       VALUES ($1, $2, $3, false, $4);`,
      [docId, summaryText, JSON.stringify({ medicines: detectedMedicines, ocr_raw: ocrResults }), now]
    );

    return NextResponse.json({
      success: true,
      message: 'Document and PaddleOCR findings saved to Neon DB',
      documentId: docId,
    });
  } catch (error: any) {
    console.error('Save OCR API Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to save document to database' },
      { status: 500 }
    );
  }
}
