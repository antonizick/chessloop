import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import DOMPurify from "dompurify";
import { bannerApi } from "@/api/banner";

export function Banner() {
  const { data: banner } = useQuery({
    queryKey: ["banner"],
    queryFn: bannerApi.get,
  });

  const [dismissed, setDismissed] = useState(false);
  const [dontShowAgain, setDontShowAgain] = useState(false);
  const dismissMut = useMutation({ mutationFn: bannerApi.dismiss });

  // A version bump (admin changed the content) makes the banner resurface even
  // if it was dismissed for the session earlier.
  useEffect(() => {
    setDismissed(false);
  }, [banner?.version]);

  if (!banner || dismissed) return null;

  function handleClose() {
    if (dontShowAgain) dismissMut.mutate();
    setDismissed(true);
  }

  return (
    <div className="bg-gold-900/30 border-b border-gold-700/40 px-4 py-2 flex items-center gap-4 text-sm text-ink-100">
      <div className="flex-1 [&_p]:m-0" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(banner.html_content) }} />
      <label className="flex items-center gap-1.5 text-xs text-ink-400 shrink-0 whitespace-nowrap">
        <input
          type="checkbox"
          checked={dontShowAgain}
          onChange={(e) => setDontShowAgain(e.target.checked)}
        />
        Don't show again
      </label>
      <button
        onClick={handleClose}
        className="text-ink-400 hover:text-ink-100 shrink-0 text-base leading-none"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}
