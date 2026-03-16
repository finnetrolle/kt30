import { LoaderCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

interface LoadingStateProps {
  title?: string;
  message?: string;
}

export function LoadingState({
  title = "Загрузка",
  message = "Подождите немного, интерфейс получает актуальные данные."
}: LoadingStateProps) {
  return (
    <Card className="border-border/70 bg-card/85">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className="rounded-full border border-primary/20 bg-primary/10 p-2 text-primary">
            <LoaderCircle className="size-4 animate-spin" />
          </div>
          <CardTitle className="text-xl">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-6 text-muted-foreground">{message}</p>
      </CardContent>
    </Card>
  );
}
