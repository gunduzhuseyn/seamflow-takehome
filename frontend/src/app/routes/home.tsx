import { SignOutButton, useUser } from "@clerk/react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/** Placeholder for the Classify page. The upload flow comes in a later unit. */
export function HomeRoute() {
  const { user } = useUser();
  const name = user?.fullName ?? user?.primaryEmailAddress?.emailAddress ?? "";

  return (
    <Card>
      <CardHeader>
        <CardDescription>SeeFood Enterprise</CardDescription>
        <CardTitle>Classify</CardTitle>
        <CardAction>
          <SignOutButton>
            <Button variant="outline" size="sm">
              Sign out
            </Button>
          </SignOutButton>
        </CardAction>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{`Signed in as ${name}.`}</p>
      </CardContent>
    </Card>
  );
}
