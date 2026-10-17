/** MSW server shared by component tests; each test adds the handlers it needs. */
import { setupServer } from "msw/node";

export const server = setupServer();
