import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useCreateMission } from '@/api/missions';

/**
 * Mirrors the FastAPI Pydantic CreateMissionRequest validation in
 * tacapes/dashboard/api/schemas.py. Constraints copied verbatim; if the
 * Python side relaxes a bound, relax it here in the same commit.
 *
 * `sectors_excluded` arrives as a comma-separated string in the UI and
 * normalizes to a string[] in the transform, keeping the dialog single-line
 * instead of a chip editor.
 */
const formSchema = z.object({
  statement: z
    .string()
    .min(20, 'At least 20 characters')
    .max(2000, 'No more than 2000 characters'),
  budget_usd: z.coerce
    .number({ message: 'Enter a number' })
    .gt(0, 'Budget must be greater than zero'),
  max_positions: z.coerce
    .number({ message: 'Enter a number' })
    .int('Must be a whole number')
    .min(1, 'At least 1')
    .max(20, 'No more than 20'),
  max_position_pct: z.coerce
    .number({ message: 'Enter a number' })
    .gt(0, 'Must be greater than 0')
    .max(1, 'No more than 1.0 (i.e. 100%)'),
  horizon_months: z.coerce
    .number({ message: 'Enter a number' })
    .int('Must be a whole number')
    .min(1, 'At least 1 month')
    .max(240, 'No more than 240 months'),
  sectors_excluded_text: z.string().optional().default(''),
  allow_shorts: z.boolean().default(false),
});

// z.coerce.number lets us bind to <input type="number"> directly: the input
// emits strings, zod coerces, the parsed output flows into onSubmit. That
// gives the form two type identities: the input shape (string|number) for the
// fields and the output shape (always numbers) for the submit handler.
type FormInput = z.input<typeof formSchema>;
type FormOutput = z.output<typeof formSchema>;

interface NewMissionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: FormInput = {
  statement: '',
  budget_usd: 20000,
  max_positions: 5,
  max_position_pct: 0.3,
  horizon_months: 24,
  sectors_excluded_text: '',
  allow_shorts: false,
};

export function NewMissionDialog({ open, onOpenChange }: NewMissionDialogProps) {
  const navigate = useNavigate();
  const create = useCreateMission();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<FormInput, undefined, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: DEFAULTS,
    mode: 'onBlur',
  });

  // Reset to defaults every time the dialog reopens so a previous failed
  // submission doesn't leave stale values around.
  useEffect(() => {
    if (open) {
      form.reset(DEFAULTS);
      setSubmitError(null);
    }
  }, [open, form]);

  async function onSubmit(values: FormOutput) {
    setSubmitError(null);
    const payload = {
      statement: values.statement.trim(),
      budget_usd: values.budget_usd,
      max_positions: values.max_positions,
      max_position_pct: values.max_position_pct,
      horizon_months: values.horizon_months,
      sectors_excluded: values.sectors_excluded_text
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      allow_shorts: values.allow_shorts,
    };
    try {
      const created = await create.mutateAsync(payload);
      toast.success('Mission queued');
      onOpenChange(false);
      navigate(`/missions/${created.id}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Could not create mission';
      setSubmitError(msg);
      toast.error(msg);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New mission</DialogTitle>
          <DialogDescription>
            Define the mandate and constraints. The pipeline runs in the background;
            you'll see it land in the list when it completes.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="space-y-4"
            data-testid="new-mission-form"
            noValidate
          >
            <FormField
              control={form.control}
              name="statement"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mission statement</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder="Buy nuclear power names positioned to win..."
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    20 to 2000 characters. Plain English; the pipeline does the parsing.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-3">
              <FormField
                control={form.control}
                name="budget_usd"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Budget (USD)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        step="100"
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        onChange={field.onChange}
                        value={field.value as number | string}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="horizon_months"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Horizon (months)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={240}
                        step="1"
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        onChange={field.onChange}
                        value={field.value as number | string}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="max_positions"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max positions</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={20}
                        step="1"
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        onChange={field.onChange}
                        value={field.value as number | string}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="max_position_pct"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max position (0.0 to 1.0)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0.01}
                        max={1}
                        step="0.05"
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        onChange={field.onChange}
                        value={field.value as number | string}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="sectors_excluded_text"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Sectors excluded (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="energy, defense" {...field} />
                  </FormControl>
                  <FormDescription>Comma-separated. Leave blank if none.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="allow_shorts"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center gap-2 space-y-0">
                  <FormControl>
                    <input
                      type="checkbox"
                      className="size-4 rounded border-input"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                    />
                  </FormControl>
                  <FormLabel className="!mt-0 text-sm">Allow short positions</FormLabel>
                </FormItem>
              )}
            />
            {submitError && (
              <p className="text-sm text-bad" role="alert">
                {submitError}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={create.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? 'Submitting...' : 'Create mission'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
