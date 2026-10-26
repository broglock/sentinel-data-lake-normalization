/* Entry point: each module registers its screens in ROUTES, then the app starts. */
import { start } from "./core.js";
import "./home.js";
import "./hunt.js";
import "./onboard.js";
import "./fields.js";
import "./approve.js";
import "./more.js";

start();
