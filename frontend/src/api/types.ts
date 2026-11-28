/** Friendly aliases for the generated OpenAPI types (`npm run api:types`). */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Me = Schemas["MeResponse"];
export type LoginResult = Schemas["LoginResponse"];
export type SessionInfo = Schemas["SessionInfo"];
export type SessionList = Schemas["SessionList"];
export type CaptchaChallenge = Schemas["CaptchaChallenge"];
export type TotpSetup = Schemas["TotpSetupResponse"];
export type RecoveryCodes = Schemas["RecoveryCodesResponse"];
export type Role = Me["role"];
export type PublicStatsResponse = Schemas["PublicStats"];
export type ClientErrorReportBody = Schemas["ClientErrorReport"];
export type Skill = Schemas["SkillOut"];
export type DeveloperSkill = Schemas["DeveloperSkillOut"];
export type DeveloperProfile = Schemas["DeveloperProfileOut"];
export type DeveloperProfileUpdate = Schemas["DeveloperProfileUpdate"];
export type ClientProfile = Schemas["ClientProfileOut"];
export type ClientProfileUpdate = Schemas["ClientProfileUpdate"];
export type StoredFileInfo = Schemas["FileOut"];
export type PortfolioItem = Schemas["PortfolioItemOut"];
export type PortfolioItemCreate = Schemas["PortfolioItemCreate"];
export type PortfolioItemUpdate = Schemas["PortfolioItemUpdate"];
export type Certificate = Schemas["CertificateOut"];
export type ExternalReview = Schemas["ExternalReviewOut"];
export type ExternalReviewUpdate = Schemas["ExternalReviewUpdate"];
export type PublicProfile = Schemas["DeveloperPublicProfile"];
export type SkillTest = Schemas["SkillTestOut"];
export type Attempt = Schemas["AttemptOut"];
export type AttemptQuestion = Schemas["AttemptQuestion"];
export type AnswerAccepted = Schemas["AnswerAccepted"];
export type AttemptResult = Schemas["AttemptResult"];

// Projects and the CPM planner (spec §7.3, §9.10, §10.2)
export type Project = Schemas["ProjectOut"];
export type ProjectDraft = Schemas["DraftOut"];
export type ProjectCreate = Schemas["ProjectCreate"];
export type ProjectUpdate = Schemas["ProjectUpdate"];
export type ProjectListItem = Schemas["ProjectListItem"];
export type ProjectListPage = Schemas["Page_ProjectListItem_"];
export type ProjectStatus = ProjectListItem["status"];
export type Slot = Schemas["SlotOut"];
export type SlotIn = Schemas["SlotIn"];
export type Milestone = Schemas["MilestoneOut"];
export type MilestoneIn = Schemas["MilestoneIn"];
export type Dependency = Schemas["DependencyIn"];
export type PreviewMilestone = Schemas["PreviewMilestone"];
export type CpmNode = Schemas["CpmNodeOut"];
export type CpmPreview = Schemas["CpmPreviewOut"];
export type Plan = Schemas["PlanOut"];
export type PlanPreviewIn = Schemas["PlanPreviewIn"];
export type PublishIn = Schemas["PublishIn"];
export type CancelIn = Schemas["CancelIn"];

// Marketplace, sealed bids and eligibility (spec §9.2, §10 Marketplace/Bids)
export type ProjectCard = Schemas["ProjectCard"];
export type ProjectDetail = Schemas["ProjectDetail"];
export type SlotCard = Schemas["SlotCard"];
export type RecommendedProject = Schemas["RecommendedProject"];
export type ProjectCardPage = Schemas["Page_ProjectCard_"];
export type BidCreate = Schemas["BidCreate"];
export type BidUpdate = Schemas["BidUpdate"];
export type Bid = Schemas["BidOut"];
export type BidPage = Schemas["Page_BidOut_"];
export type BidDetail = Schemas["BidDetailOut"];
export type BidReason = Schemas["BidReason"];
export type EligibilityIn = Schemas["EligibilityIn"];
export type EligibilityOut = Schemas["EligibilityOut"];
export type ClientBids = Schemas["ClientBidsOut"];
export type ClientBid = Schemas["ClientBidOut"];
export type ConstraintCheck = Schemas["ConstraintCheck"];
export type TermsChange = Schemas["TermsChange"];
export type TermsPreview = Schemas["TermsPreviewOut"];
// Role assessment (role assessment spec §9).
export type AssessmentStatus = Schemas["AssessmentStatusOut"];
export type AssessmentStatusName = AssessmentStatus["status"];
export type AssessmentBlueprint = Schemas["BlueprintOut"];
export type AssessmentResult = Schemas["AssessmentResultOut"];
export type AssessmentAttempt = Schemas["AttemptStateOut"];
export type AssessmentStarted = Schemas["StartedOut"];
export type AssessmentQuestion = Schemas["QuestionOut"];
export type AssessmentAnswer = Schemas["AnswerOut"];
export type FocusEventResult = Schemas["FocusEventOut"];
export type FocusEventType = Schemas["FocusEventIn"]["type"];
export type HeartbeatResult = Schemas["HeartbeatOut"];
export type RoleAssessmentHistoryItem = Schemas["HistoryItemOut"];
export type AssessmentLine = Schemas["AssessmentLineOut"];
export type PublicRoleAssessment = Schemas["PublicRoleAssessment"];
export type FlaggedAssessment = Schemas["FlaggedItemOut"];
export type AssessmentDetail = Schemas["AttemptDetailOut"];
export type AdminQuestion = Schemas["QuestionAdminOut"];
// Phase 6: reputation (spec §10.2 Reputation, §13.5 #16).
export type DeveloperReputation = Schemas["DeveloperReputation"];
export type ReputationParameters = Schemas["ReputationParameters"];
export type ReputationHistoryItem = Schemas["ReputationHistoryItem"];
export type ReputationChange = Schemas["ReputationChange"];
export type ReputationHistoryPage = Schemas["Page_ReputationHistoryItem_"];

// Team formation (spec §9.2–§9.8, §10.2 Formation; Phase 7)
export type FormationRunCreate = Schemas["FormationRunCreate"];
export type FormationRunAccepted = Schemas["FormationRunAccepted"];
export type FormationRun = Schemas["FormationRunOut"];
export type FormationRunSummary = Schemas["FormationRunSummary"];
export type RunResult = Schemas["RunResult"];
export type TeamMember = Schemas["TeamMemberOut"];
export type TeamOption = Schemas["TeamOption"];
export type ConfirmTeam = Schemas["ConfirmOut"];
export type BidExplanationOut = Schemas["BidExplanationOut"];
export type JobOut = Schemas["JobOut"];
export type Preset = FormationRunCreate["preset"];

// Team lifecycle and notifications (spec §10.2 Team, Notifications; Phase 8)
export type TeamForClient = Schemas["TeamForClient"];
export type TeamForMember = Schemas["TeamForMember"];
export type TeamView = TeamForClient | TeamForMember;
export type TeamMemberForClient = Schemas["TeamMemberForClient"];
export type TeamMemberForMember = Schemas["TeamMemberForMember"];
export type MyInvitations = Schemas["MyInvitationsOut"];
export type MyInvitation = Schemas["MyInvitationOut"];
export type MyMembership = Schemas["MyMembershipOut"];
export type ClientTeamCard = Schemas["ClientTeamCard"];
export type RepairOut = Schemas["RepairOut"];
export type RepairCandidate = Schemas["RepairCandidate"];
export type LeadChangeRequest = Schemas["LeadChangeRequestOut"];
export type NotificationItem = Schemas["NotificationOut"];
export type NotificationPage = Schemas["Page_NotificationOut_"];
export type NotificationPreferences = Schemas["Preferences"];
export type PreferenceItem = Schemas["PreferenceItem"];
export type ActionResult = Schemas["ActionOut"];

// Workspace: tasks (spec §7.5, §10.2 Tasks; D143, D144, D148, D168, D172)
export type TaskStatus = Schemas["TaskCard"]["status"];
export type TaskDifficulty = Schemas["TaskCard"]["difficulty"];
export type TaskCard = Schemas["TaskCard"];
export type TaskDetail = Schemas["TaskDetail"];
export type TaskPage = Schemas["Page_TaskCard_"];
export type TaskCreate = Schemas["TaskCreate"];
export type TaskPatch = Schemas["TaskPatch"];
export type TaskMove = Schemas["TaskMove"];
export type MoveOption = Schemas["MoveOption"];
export type TaskEvidence = Schemas["EvidenceOut"];
export type EvidenceCreate = Schemas["EvidenceCreate"];
export type PersonRef = Schemas["PersonRef"];

// Workspace: weekly check-ins (spec §10.2 Check-ins; D145)
export type Checkin = Schemas["CheckinOut"];
export type CheckinCreate = Schemas["CheckinCreate"];
export type CheckinFeed = Schemas["CheckinFeed"];

// Workspace: comments and discussion (spec §10.2; D146)
export type CommentItem = Schemas["CommentOut"];
export type CommentPage = Schemas["Page_CommentOut_"];
export type Thread = Schemas["ThreadOut"];
export type ThreadPage = Schemas["Page_ThreadOut_"];
export type ThreadCreate = Schemas["ThreadCreate"];

// Workspace: project files (spec §10.2 Files; D147)
export type ProjectFile = Schemas["ProjectFile"];
export type ProjectFilePage = Schemas["Page_ProjectFile_"];

// Workspace: monitoring (spec §10.2 Monitoring; D151, D152)
export type DashboardForClient = Schemas["DashboardForClient"];
export type DashboardForMember = Schemas["DashboardForMember"];
export type Dashboard = DashboardForClient | DashboardForMember;
export type RiskItem = Schemas["ProjectRisk"];
export type RiskList = Schemas["RiskList"];
export type ActivityItem = Schemas["ActivityItem"];
export type ActivityPage = Schemas["Page_ActivityItem_"];
export type EvidenceSummary = Schemas["EvidenceSummary"];
export type MemberEvidence = Schemas["MemberEvidence"];
export type PlanForecast = Schemas["PlanForecast"];
export type ForecastNode = Schemas["ForecastNode"];
