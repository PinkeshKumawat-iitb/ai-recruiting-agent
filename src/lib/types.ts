export interface Profile { id?: string; full_name: string; email: string; role: "recruiter" | "candidate"; phone?: string | null }
export interface Screening { summary: string; overall_score: number; recommendation: string; matching_skills?: string[]; gaps_to_clarify?: string[]; evidence?: string[] }
export interface Application { id: string; job_id?: string; job_title: string; candidate_id?: string; candidate_name?: string; candidate_email?: string; status: string; has_resume?: boolean; resume_filename?: string | null; screening?: Screening | null; applied_at: string }
export interface Job { id: string; recruiter_id?: string; title: string; department: string; location: string; employment_type: string; description: string; requirements: string[]; status: string; applicant_count?: number; created_at?: string }
export interface Competency { name: string; score: number; evidence: string }
export interface Evaluation { summary: string; recommendation: string; overall_score: number; competencies: Competency[]; strengths: string[]; follow_up: string[] }
export interface Interview { id: string; application_id: string; candidate_name: string; job_title: string; scheduled_at: string | null; language: string; status: string; evaluation?: Evaluation | null; completed_at?: string | null }
export interface Turn { speaker: "candidate" | "interviewer"; content: string; language_code?: string | null; created_at?: string }
export interface InterviewDetail extends Interview { candidate_name: string; job_description: string; turns: Turn[] }
export interface InterviewReport { candidate_name: string; candidate_email: string; job_title: string; language: string; evaluation: Evaluation; transcript: Turn[] }
export interface Notification { id: string; title: string; body: string; link?: string | null; read: boolean; created_at: string }
export interface RecruiterDashboard { counts: { active_jobs: number; candidates: number; interviews: number; reports: number }; jobs: Job[]; applications: Application[]; upcoming_interviews: Interview[] }
