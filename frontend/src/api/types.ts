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
