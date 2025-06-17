class AddErrorMessageToPdfResults < ActiveRecord::Migration[8.0]
  def change
    add_column :pdf_results, :error_message, :text
  end
end
