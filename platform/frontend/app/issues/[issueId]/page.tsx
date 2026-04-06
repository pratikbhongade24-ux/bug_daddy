import { notFound } from "next/navigation";

import { IssueDetailClient } from "@/components/issue-detail-client";
import { getIssueDetail } from "@/lib/api";

export default async function IssueDetailPage({ params }: { params: Promise<{ issueId: string }> }) {
  const { issueId } = await params;
  const issue = await getIssueDetail(issueId);

  if (!issue) {
    notFound();
  }

  return <IssueDetailClient initialIssue={issue} />;
}
