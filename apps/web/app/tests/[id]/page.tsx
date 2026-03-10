import { GeneratedTestViewer } from "../../../components/generated-test-viewer";

export default async function GeneratedTestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GeneratedTestViewer testId={id} />;
}
