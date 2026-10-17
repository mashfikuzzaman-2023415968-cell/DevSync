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
