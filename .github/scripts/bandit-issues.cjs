const fs = require("node:fs");
const crypto = require("node:crypto");

module.exports = async ({ github, context, core }) => {
  if (context.eventName !== "push") return;

  const report = JSON.parse(
    fs.readFileSync("bandit-report.json", "utf8")
  );

  if (!Array.isArray(report.results)) {
    throw new Error("Invalid Bandit report: results array is missing");
  }

  if (report.errors?.length) {
    core.setFailed("Bandit could not scan some files; inspect the report");
  }

  if (report.results.length === 0) {
    core.info("No Bandit findings to publish");
    return;
  }

  const issues = await github.paginate(
    github.rest.issues.listForRepo,
    {
      ...context.repo,
      state: "all",
      creator: "github-actions[bot]",
      per_page: 100,
    }
  );

  const repoUrl =
    `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}`;
  const runUrl = `${repoUrl}/actions/runs/${context.runId}`;
  const occurrences = new Map();

  for (const finding of report.results) {
    const file = finding.filename.replace(/^\.\//, "");

    // Remove line numbers from Bandit's code excerpt.
    const code = finding.code
      .split("\n")
      .map((line) => line.replace(/^\d+\s/, "").trim())
      .join("\n")
      .trim();

    const identity = JSON.stringify([finding.test_id, file, code]);

    // Distinguish identical findings appearing multiple times in a file.
    const occurrence = (occurrences.get(identity) || 0) + 1;
    occurrences.set(identity, occurrence);

    const fingerprint = crypto
      .createHash("sha256")
      .update(JSON.stringify([identity, occurrence]))
      .digest("hex");

    const marker = `<!-- bandit-finding:${fingerprint} -->`;
    const sourcePath = file.split("/").map(encodeURIComponent).join("/");
    const sourceUrl =
      `${repoUrl}/blob/${context.sha}/${sourcePath}#L${finding.line_number}`;

    const title =
      `[Bandit ${finding.test_id}] ${file}:${finding.line_number}`
        .slice(0, 256);

    const body = [
      marker,
      "Automatically maintained by the Bandit workflow.",
      "",
      `**Rule:** ${finding.test_id} — ${finding.test_name}`,
      `**Severity:** ${finding.issue_severity}`,
      `**Confidence:** ${finding.issue_confidence}`,
      "",
      finding.issue_text,
      "",
      `**Last detected in:** \`${context.ref}\``,
      `[Source code](${sourceUrl}) · [Workflow run](${runUrl})`,
    ].join("\n");

    const existing = issues.find(
      (issue) => !issue.pull_request && issue.body?.includes(marker)
    );

    if (existing) {
      await github.rest.issues.update({
        ...context.repo,
        issue_number: existing.number,
        title,
        body,
      });
      core.info(`Updated issue #${existing.number}`);
    } else {
      const { data } = await github.rest.issues.create({
        ...context.repo,
        title,
        body,
      });
      issues.push(data);
      core.info(`Created issue #${data.number}`);
    }
  }
};