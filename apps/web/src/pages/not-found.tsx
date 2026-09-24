import { Link } from "react-router";

import { EmptyState } from "@/components/app/states";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      description="The page you are looking for does not exist."
      action={
        <Button size="sm" asChild>
          <Link to="/">Go to dashboard</Link>
        </Button>
      }
      className="h-full"
    />
  );
}
