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
export type PublicProfile = Schemas["DeveloperPublicProfile"];
export type SkillTest = Schemas["SkillTestOut"];
export type Attempt = Schemas["AttemptOut"];
export type AttemptQuestion = Schemas["AttemptQuestion"];
export type AnswerAccepted = Schemas["AnswerAccepted"];
export type AttemptResult = Schemas["AttemptResult"];

// Projects and the CPM planner (spec §7.3, §9.10, §10.2)
export type Project = Schemas["ProjectOut"];
export type ProjectCreate = Schemas["ProjectCreate"];
export type ProjectUpdate = Schemas["ProjectUpdate"];
export type ProjectListItem = Schemas["ProjectListItem"];
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
