export type QualityGateStatus = "HIGH_CONFIDENCE" | "NEEDS_CHECK" | "LOW_QUALITY";
export type ExtractionStatus = "PENDING_USER_CONFIRMATION" | "CONFIRMED" | "DISCARDED";
export type FieldValidationFlag = "ok" | "check" | "low" | "missing" | "empty";
export type MedicineStatus = "OK" | "CHECK" | "LOW";

export interface FieldMeta {
  read: string | null;
  conf: number | null;
  flag: FieldValidationFlag;
}

export interface MedicineIssue {
  field: string;
  code: string;
  msg: string;
}

export interface MedicineDbInfo {
  verified: boolean;
  db_name: string | null;
  generic: string | null;
  composition: string | null;
  uses: string | null;
  score: number | null;
}

export interface MedicineRecord {
  name: string | null;
  form: string | null;
  strength: string | null;
  dose: string | null;
  frequency: string | null;
  timing: string | null;
  duration: string | null;
  route: string | null;
  fields?: Record<string, FieldMeta>;
  status?: MedicineStatus;
  min_conf?: number;
  issues?: MedicineIssue[];
  warnings?: string[];
  corrected?: string[];
  ambiguity_note?: string | null;
  db?: MedicineDbInfo;
}

export interface VitalRecord {
  name: string;
  value: string | null;
  conf?: number | null;
  flag?: "ok" | "check" | "low";
  kind?: string;
  parsed?: Record<string, any>;
}

export interface PatientInfo {
  name: string | null;
  uhid: string | null;
  age: string | null;
  sex: string | null;
  ward_bed: string | null;
  name_conf?: number | null;
}

export interface DoctorInfo {
  name: string | null;
  reg_no: string | null;
}

export interface PrescriptionRecord {
  patient: PatientInfo;
  hospital: string | null;
  doctor: DoctorInfo;
  date_raw: string | null;
  date_iso: string | null;
  vitals: VitalRecord[];
  diagnosis: string[];
  allergies: string[];
  medicines: MedicineRecord[];
  advice: string[];
  follow_up: string | null;
}

export interface QualityGate {
  status: QualityGateStatus;
  reasons: string[];
}

export interface ExtractionPayload {
  extraction_id: number;
  ocr_id: number;
  status: ExtractionStatus;
  llm_model: string;
  patient_id?: string;
  duplicate?: boolean;
  gate: QualityGate;
  warnings: string[];
  record: PrescriptionRecord;
}

export interface ExtractionSummaryItem {
  extraction_id: number;
  ocr_id: number;
  llm_model: string;
  status: ExtractionStatus;
  created_at: string;
  patient_id: string;
  filename: string;
  avg_conf: number;
  gate: QualityGate;
  record: PrescriptionRecord;
}

export interface RawOcrLine {
  id: string;
  row: number;
  text: string;
  conf: number;
  x: number;
  y: number;
}

export interface RawOcrData {
  id: number;
  filename: string;
  patient_id: string;
  ocr_engine: string;
  avg_conf: number;
  image_w: number;
  image_h: number;
  created_at: string;
  lines: RawOcrLine[];
}

export interface EditRecord {
  path: string;
  machine: any;
  confirmed: any;
}

export interface ConfirmResult {
  prescription_id: number;
  patient_id: string;
  rx_date: string;
  edits: EditRecord[];
  observations_saved: number;
  observations_skipped: Array<{ name: string; value: string; reason: string }>;
}

export interface ConfirmedPrescription {
  id: number;
  extraction_id: number;
  patient_id: string;
  rx_date: string;
  hospital: string | null;
  doctor: string | null;
  doctor_reg_no: string | null;
  data: PrescriptionRecord;
  edits: EditRecord[];
  confirmed_by: string | null;
  confirmed_at: string;
}

export interface ObservationRecord {
  id: number;
  patient_id: string;
  prescription_id: number;
  obs_date: string;
  kind: string;
  systolic?: number | null;
  diastolic?: number | null;
  value?: number | null;
  unit?: string | null;
  raw_text?: string | null;
  created_at: string;
}

export interface HealthResponse {
  ok: boolean;
  ocr: string;
  medicine_names_indexed: number;
  time: string;
}
