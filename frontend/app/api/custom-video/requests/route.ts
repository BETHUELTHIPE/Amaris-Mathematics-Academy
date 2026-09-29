import { createStudentCustomVideoRequest } from "@/lib/student-api";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const result = await createStudentCustomVideoRequest(formData);
    return Response.json(result, { status: 201 });
  } catch {
    return Response.json(
      {
        detail:
          "We could not create your custom-video request. Check your files and try again.",
      },
      { status: 400 },
    );
  }
}
