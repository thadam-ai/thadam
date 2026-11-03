import fs from "node:fs";
const packages = [
    "react",
    "lossless-json",
    "react-dom",
    "scheduler",
    "lucide-react",
    "@fontsource-variable/inter",
];
const notice = packages
    .map(
        (name) =>
            `${name}\n${"=".repeat(name.length)}\n\n${fs.readFileSync(fs.existsSync(`node_modules/${name}/LICENSE`) ? `node_modules/${name}/LICENSE` : `node_modules/${name}/LICENSE.md`, "utf8")}`,
    )
    .join("\n\n");
fs.writeFileSync(
    "../src/thadam/dashboard/static/THIRD_PARTY_NOTICES.txt",
    notice,
);
