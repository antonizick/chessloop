import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";

interface VideoLinksSectionProps {
  libraryId: string;
  canEdit: boolean;
}

export function VideoLinksSection({ libraryId, canEdit }: VideoLinksSectionProps) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);

  const { data: links = [] } = useQuery({
    queryKey: ["video-links", libraryId],
    queryFn: () => librariesApi.listVideoLinks(libraryId),
  });

  const addMut = useMutation({
    mutationFn: () => librariesApi.addVideoLink(libraryId, { title: title.trim(), url: url.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["video-links", libraryId] });
      setTitle("");
      setUrl("");
      setShowForm(false);
      setUrlError(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (linkId: string) => librariesApi.deleteVideoLink(libraryId, linkId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video-links", libraryId] }),
  });

  const validateAndSubmit = () => {
    if (!url.trim().startsWith("http://") && !url.trim().startsWith("https://")) {
      setUrlError("URL must start with http:// or https://");
      return;
    }
    setUrlError(null);
    addMut.mutate();
  };

  if (!canEdit && links.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-ink-300">Video Links</h3>
        {canEdit && !showForm && (
          <button
            className="btn-ghost text-xs py-1 px-2"
            onClick={() => setShowForm(true)}
            disabled={links.length >= 10}
            title={links.length >= 10 ? "Maximum 10 links reached" : "Add a training video link"}
          >
            + Add link
          </button>
        )}
      </div>

      {links.length === 0 && canEdit && (
        <p className="text-xs text-ink-500">No video links yet.</p>
      )}

      <div className="flex flex-col gap-1">
        {links.map((link) => (
          <div key={link.id} className="flex items-center gap-2">
            <a
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center gap-2 px-3 py-2 rounded bg-ink-800 border border-ink-700 hover:border-gold-500/50 hover:bg-ink-750 text-sm text-ink-200 hover:text-gold-300 transition-colors"
            >
              <span className="text-gold-500 shrink-0">▶</span>
              <span className="truncate">{link.title}</span>
            </a>
            {canEdit && (
              <button
                className="btn-ghost text-xs py-1 px-2 text-red-400 hover:text-red-300 shrink-0"
                onClick={() => deleteMut.mutate(link.id)}
                disabled={deleteMut.isPending}
                title="Remove link"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>

      {canEdit && showForm && (
        <div className="flex flex-col gap-2 p-3 bg-ink-800 border border-ink-700 rounded">
          <div className="flex flex-col gap-1">
            <input
              type="text"
              className="input text-sm"
              placeholder="Link title (e.g. Full Opening Course)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              maxLength={128}
            />
          </div>
          <div className="flex flex-col gap-1">
            <input
              type="url"
              className="input text-sm"
              placeholder="https://youtube.com/..."
              value={url}
              onChange={(e) => { setUrl(e.target.value); setUrlError(null); }}
              maxLength={500}
            />
            {urlError && <p className="text-xs text-red-400">{urlError}</p>}
          </div>
          <div className="flex gap-2 justify-end">
            <button
              className="btn-ghost text-xs py-1 px-2"
              onClick={() => { setShowForm(false); setTitle(""); setUrl(""); setUrlError(null); }}
              disabled={addMut.isPending}
            >
              Cancel
            </button>
            <button
              className="btn-primary text-xs py-1 px-2"
              onClick={validateAndSubmit}
              disabled={addMut.isPending || !title.trim() || !url.trim()}
            >
              {addMut.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
