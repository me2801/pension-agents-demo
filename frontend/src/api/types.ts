/** Friendly names for the API types generated from the backend's OpenAPI spec (schema.d.ts). */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type ChatEvent = Schemas["ChatEventSchema"];
export type Conversation = Schemas["Conversation"];
export type Message = Schemas["Message"];
export type Token = Schemas["Token"];
export type User = Schemas["User"];
export type WorkflowInfo = Schemas["WorkflowInfo"];
