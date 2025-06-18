class HomeController < ApplicationController
  def index
    @url = "https://www.google.com"
  end

  def generate_pdf
    url = params[:url] || "https://www.google.com"

    response = HTTParty.post(
      ENV["PYTHON_SERVICE_URL"] + "/generate_pdf",
      body: { url: url }.to_json,
      headers: { "Content-Type" => "application/json" }
    )

    parsed = response.parsed_response

    if response.code == 202 && parsed["task_id"]
      redirect_to home_pdf_status_path(task_id: parsed["task_id"])
    else
      render json: { error: parsed["detail"] || "Failed to initiate PDF generation" }, status: :internal_server_error
    end
  end

  def pdf_status
    @task_id = params[:task_id]
    if @task_id.blank?
      redirect_to root_path, alert: "Invalid PDF task ID."
      return
    end

    response = HTTParty.get(ENV["PYTHON_SERVICE_URL"] + "/pdf_status/#{@task_id}")
    @status = response.parsed_response

    if @status["status"] == "completed"
      pdf_url = @status["pdf_url"]
      pdf_file_name = @status["pdf_file_name"]

      pdf_file_response = HTTParty.get(pdf_url)

      if pdf_file_response.success?
        send_data pdf_file_response.body, filename: pdf_file_name, type: "application/pdf", disposition: "attachment"
      else
        flash[:alert] = "Failed to download PDF: #{pdf_file_response.body}"
        redirect_to root_path
      end

    elsif @status["status"] == "failed"
      flash[:alert] = "PDF generation failed: #{@status["error"]}"
      redirect_to root_path
    else
      render :pdf_status
    end
  end
end
