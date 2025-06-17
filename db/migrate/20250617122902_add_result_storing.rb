class AddResultStoring < ActiveRecord::Migration[8.0]
  def change
    create_table :pdf_results do |t|
      t.string :filename
      t.string :status
      t.integer :user_id

      t.timestamps
    end
  end
end
