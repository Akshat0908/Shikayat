export type Stage = 'draft' | 'sent' | 'deflection' | 'escalated' | 'offered' | 'resolved';
export interface CaseRecord { id: string; title: string; company_id: string; amount_inr: number; status: Stage; level: 'L2' | 'L3'; strength_score: number; recovered_inr: number; created_at: string; facts_json: { order_id: string | null; purchase_date: string | null; missing_info: string[]; field_confidence: Record<string, number> }; }
export interface TimelineEvent { id: string; actor: 'ai' | 'user' | 'company' | 'system'; title: string; reason: string; at: string; }
export interface EmailDraft { subject: string; body: string; deadline_date: string; cited_refs: string[]; }
